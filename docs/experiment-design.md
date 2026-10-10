# Экспериментальный протокол

## Гипотеза

Provenance-aware модель должна сохранять более высокий Recall при
`FPR <= 0.1%` в условиях пропущенных источников, чем жёсткие правила и
стандартный Isolation Forest, особенно на сценариях с частичной
наблюдаемостью.

## Сценарии

Стенд генерирует независимые run:

| Scenario | Назначение |
| --- | --- |
| `stable` | Стабильное штатное состояние |
| `legit_update` | Корректный NRF update → notify → смена маршрута |
| `delayed_notify` | Легитимный notify с задержкой, создающей временное рассогласование |
| `udm_recovery` | Отказ/восстановление UDM |
| `cache_observer_skew` | Benign: краткое устаревшее наблюдение AUSF при корректном NRF/route |
| `route_observer_skew` | Benign: краткое устаревшее наблюдение route при корректном NRF/AUSF |
| `forged_notify` | Моделируемый постэффект cache poisoning без изменения NRF |
| `forged_notify_missing` | То же при деградации notify-телеметрии |
| `silent_dual_divergence` | Симулируемое устойчивое AUSF+route рассогласование без bad-notify evidence |
| `persistent_cache_divergence` | Симулируемое устойчивое cache-only рассогласование |
| `persistent_route_divergence` | Симулируемое устойчивое route-only рассогласование |
| `legit_update_missing` | Легитимный переход при неполной наблюдаемости |

Observer-skew сценарии меняют только наблюдаемое значение одного источника на
коротком интервале; underlying simulated state не меняется. Они создают
benign semantic support, который пересекается со support устойчивого
single-source divergence. Это специально лишает semantic guard идеальной
разделимости и проверяет, может ли ML использовать длительность,
согласованность независимых источников и provenance.

Все attack-like сценарии выше существуют только как симулируемый post-effect.
Стенд не создаёт и не отправляет forged SBI payload в Open5GS.

## Признаки

Основная модель получает:

- `delta_nrf_ausf` — наблюдаемое расхождение NRF и AUSF;
- `delta_route` — расхождение NRF и фактического маршрута;
- `delta_notify` — нарушение семантики подписки/доверия уведомления;
- `delta_time` — изменение локального состояния без недавнего NRF update;
- `m_*` — маски доступности источников;
- `prov_*` — provenance-покрытие конкретного сравнения;
- `recovery_active` — эксплуатационный контекст;
- `obs_fraction` — доля доступных независимых источников.

## Базовые методы

1. `rules`: детерминированная оценка семантических противоречий.
2. `semantic_guard`: exact deterministic baseline для semantic support,
   используемого PA-TEF.
3. `consensus_guard`: deterministic source-consensus baseline. Bad-notify
   escalates immediately, dual-source divergence requires two consecutive
   samples, while single-source divergence requires a full 12-sample
   persistence window.
4. `isolation_forest`: unsupervised baseline, обучаемый только на benign train.
5. `provenance_aware`: supervised baseline, явно использующий маски и
   provenance.
6. `patef`: learned evidence fusion поверх того же semantic support.

## Разделение данных

Разделение train/calibration/test выполняется **по run_id**, чтобы соседние
точки одного временного эпизода не попадали в разные выборки.

Дополнительно используется scenario-disjoint holdout: каждый тип сценария
полностью исключается из training и calibration и оценивается как unseen test.

Порог каждого детектора выбирается только на calibration set по
эмпирическому benign score distribution для целевого FPR.

## Метрики

Основные:

- `Recall@FPR=0.1%`;
- фактический FPR на test;
- median detection delay после attack_start;
- доля attack runs, где детектор сработал.

Дополнительно запускается абляция `no_nrf/no_ausf/no_route/no_notify`.

Абляция выполняется **до feature engineering**: скрываются исходные endpoint,
event и mask-поля выбранного источника, после чего semantic/temporal/provenance
признаки строятся заново. Производные признаки, рассчитанные до абляции, не
могут переноситься в ablated dataset. Все варианты используют тот же
`random_state` и run-level split, что основной benchmark.

## Внешние Open5GS controls

Реальные benign/recovery traces и контрфактический replay оцениваются тремя
детекторами на одном и том же входе и synthetic calibration:

- `semantic_guard` — исходный deterministic semantic comparator;
- `consensus_guard` — source-consensus comparator, который на synthetic
  hard-generalization benchmark удерживает target FPR;
- `patef` — learned comparator.

Workflow success означает, что реальная A→B→A лаборатория и её evidence
валидны: NRF, AUSF-cache и фактический route дают ожидаемые переходы, а benign
trace не вызывает alert у сравниваемых детекторов. Контрфактический replay
используется как **research transfer measurement**, а не как условие зелёного
CI.

Для каждого детектора сохраняются threshold, max risk, recall и FPR на
контрфактическом post-effect, а также флаг `meets_external_target`.
Это специально отделяет исправность стенда от качества текущего метода:
отрицательный detector-result остаётся видимым в artifact, но не маскируется
как инфраструктурная ошибка.

На текущем 12-сценарном hard-generalization benchmark `consensus_guard`
даёт pooled scenario-disjoint Recall 0.914 при FPR 0 и worst-scenario FPR 0.
PA-TEF имеет более высокий Recall 0.94497, но pooled unseen FPR 0.009938,
что выше целевых 0.001. `semantic_guard` при строгом low-FPR threshold
теряет recall полностью. Поэтому `consensus_guard` является текущим
constrained baseline-кандидатом, но его статус должен подтверждаться real
Open5GS controls, а не только synthetic matrix.

## Source-consensus hypothesis

Calibration diagnostics показывают, что max-score benign ties у
`semantic_guard` создаются короткими single-source observer-skew эпизодами.
Это мотивирует отдельную, заранее интерпретируемую гипотезу: подтверждение от
двух независимых state-observer имеет большую доказательную силу, чем
расхождение только одного observer.

`consensus_guard` поэтому использует asymmetric persistence:

- bad/untrusted notify: immediate;
- dual-source state conflict: минимум 2 последовательных sample;
- single-source state conflict: минимум 12 последовательных sample.

Число 12 соответствует уже существующему максимальному temporal aggregation
window, а не длине конкретного observer-skew сценария. Цена такой
консервативности должна измеряться через detection delay и recall на
persistent single-source divergence.

Этот baseline не заменяет `semantic_guard`; оба сохраняются, чтобы можно было
отделить выигрыш от source-consensus semantics от learned fusion.

Real Open5GS scoring сохраняет detector-specific summaries для всех трёх
методов. Для failover counterfactual workflow сообщает recall/FPR и
`meets_external_target` отдельно; counterfactual result остаётся research
measurement и не превращается в инфраструктурный pass/fail.

## Calibration / transfer diagnostics

Benchmark сохраняет `calibration-diagnostics.csv`,
`calibration-max-score-ties.csv` и
`generalization-risk-register.csv`.

Первый отчёт показывает, достижим ли целевой FPR при наблюдаемом calibration
score distribution. Для дискретных детекторов важен случай, когда большое число
benign samples связано на максимальном score: тогда корректный threshold может
оказаться выше максимума, и детектор будет иметь нулевой recall при требуемом
FPR. Второй отчёт показывает, какие сценарии создают эти max-score ties.

`generalization-risk-register.csv` сортирует scenario-disjoint folds по
превышению целевого FPR. Это отделяет две разные проблемы: calibration ties на
известных benign данных и transfer/generalization failures на полностью
невиденных benign сценариях.

GitHub Actions также пишет `calibration-transfer.json` с компактным
машиночитаемым summary для semantic guard и PA-TEF.

## Критерий, при котором ML не оправдан

Если `semantic_guard` при равном или меньшем FPR стабильно имеет не худшие
Recall и detection delay на run-level, scenario-disjoint и leak-free ablation
оценках, learned fusion не имеет подтверждённого incremental value и не должен
позиционироваться как deployable преимущество.
