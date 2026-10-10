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
- `consensus_guard` — deterministic source-consensus comparator;
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
удерживает scenario-disjoint FPR на 0 и даёт pooled attack recall 0.914,
в то время как PA-TEF имеет более высокий recall, но превышает целевой FPR на
невиденных observer-skew сценариях. `semantic_guard` при строгой calibration
теряет attack recall из-за max-score ties.

### Real consensus transfer result

В Open5GS A→B→A validation run `38051681251` все три метода дали 0 benign
alerts на реальной трассе. На counterfactual post-effect, построенном из той же
реальной AUSF/route evidence, результаты были:

- `semantic_guard`: recall 0.0, FPR 0.0;
- `consensus_guard`: recall 0.8 (4/5 attack samples), FPR 0.0;
- `patef`: recall 0.0, FPR 0.0.

Таким образом, source-consensus semantics переносится на real-derived trace
лучше двух прежних методов, но строгий внешний target recall=1.0 пока не
достигнут.

Повторный validation run `38052364939` дополнительно разделил sample-level
recall и episode-level detection. Для `consensus_guard` те же 4/5 alert
samples соответствуют **1/1 обнаруженному attack run** с
`median_detection_delay=1` sample и FPR 0. `semantic_guard` и PA-TEF не
обнаружили этот attack run при своих low-FPR thresholds.

Строгий `meets_external_target` намеренно остаётся sample-level и не меняется
после этого наблюдения; run-detection/delay публикуются как отдельные метрики.
Этот результат является evidence в пользу дальнейшего исследования, а не claim
о deployable detector.

## Независимые real-replicates

Для оценки межзапускового разброса используется отдельная 8-run Open5GS
matrix. Каждый replicate выполняется на свежем GitHub-hosted runner с новым
контейнерным 5G Core и новой регистрацией UDM NF instances. Протокол
baseline → UDM-B failover → UDM-A recovery остаётся фиксированным, поэтому
разброс отражает воспроизводимость лабораторного процесса и timing/evidence
extraction, а не изменение сценария.

Для continuous metrics публикуются mean, sample SD, median, IQR, min/max и
percentile bootstrap 95% CI по replicate-level observations. Для бинарных
outcome (attack run detected, benign run alert-free, target met) публикуется
Wilson 95% CI. При n=8 эти интервалы интерпретируются как exploratory
uncertainty estimates, а не как population-level production guarantee.

Detector alert не делает replicate невалидным и не исключается из статистики.
Исключение допускается только при повреждённой/неполной реальной evidence
последовательности NRF/AUSF/route. Aggregate job требует минимум 6 валидных
запусков из 8. Полная методика описана в
`docs/replicated-real-study.md`.

### Replicated real result

Run `38055330313` produced 8/8 valid fresh Open5GS instantiations with
16/16 unique UDM NF instance IDs. `consensus_guard` reproduced sample recall
0.8, FPR 0, attack-run detection 8/8 and median detection delay 1 sample in
every run; both `semantic_guard` and PA-TEF detected 0/8 attack runs at their
low-FPR thresholds. All three methods produced zero benign alerts in all eight
real failover traces.

The Wilson 95% CI for the observed `consensus_guard` attack-run detection
proportion 8/8 is [0.6756, 1.0000]. Detector-level replicate variance is zero
under this fixed protocol, while failover duration has mean 27.229 s and
SD 1.041 s and total experiment duration has mean 59.892 s and SD 1.846 s.
The complete dispersion table and bootstrap intervals are documented in
`docs/replicated-real-study.md`.

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

## Publication robustness: sensitivity and degraded telemetry

Перед публикацией параметры `consensus_guard` проверяются отдельным
development-only sweep, а robustness к неполной телеметрии — на новых real
Open5GS benign traces.

Sensitivity run `38058210231` проверяет single-source persistence
4/6/8/10/12/16 и dual-source persistence 1/2/3/4 без использования real test
labels. Reference 2/12 даёт scenario-disjoint FPR 0, recall 0.914 и median
delay 1. Единственная Pareto-точка в этой сетке — 1/8: FPR 0, recall 0.9491,
delay 0. Значения single=4/6 приводят к calibration cliff и нулевому attack
recall при целевом FPR. Поэтому 2/12 считается консервативным reference, а не
оптимизированной конфигурацией.

Real degradation run `38058506496` включает 4/4 валидных свежих Open5GS
A→B→A лаборатории и 15 observer-view вариантов на каждый run: полное отсутствие
источников, burst-loss, AUSF/route lag и notify delay. Underlying real state
остаётся benign. Для всех 15 вариантов каждый из трёх методов был alert-free
во всех 4 независимых runs. Для наблюдаемой доли 4/4 Wilson 95% CI составляет
[0.5101, 1.0000]; 15 views одного run коррелированы и не считаются независимыми
испытаниями.

Полная методика и интерпретация находятся в
`docs/publication-robustness.md`.

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
