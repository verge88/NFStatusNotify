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
- `obs_fraction` — доля доступных независимых источников;
- `*_age_steps` — optional provenance freshness источников;
- `fresh/stale_conflict_*` — source-symmetric конфликтные признаки,
  разделяющие свежую divergence и устаревшее observer evidence.

## Базовые методы

1. `rules`: детерминированная оценка семантических противоречий.
2. `semantic_guard`: exact deterministic baseline для semantic support,
   используемого PA-TEF.
3. `isolation_forest`: unsupervised baseline, обучаемый только на benign train.
4. `provenance_aware`: supervised baseline, явно использующий маски и
   provenance.
5. `patef`: learned evidence fusion поверх того же semantic support.

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

Дополнительно запускается абляция
`no_nrf/no_ausf/no_route/no_notify/no_freshness`.

Абляция выполняется **до feature engineering**: скрываются исходные endpoint,
event и mask-поля выбранного источника, после чего semantic/temporal/provenance
признаки строятся заново. Производные признаки, рассчитанные до абляции, не
могут переноситься в ablated dataset. Все варианты используют тот же
`random_state` и run-level split, что основной benchmark.

## Внешние Open5GS controls

Реальные benign/recovery traces и контрфактический replay оцениваются двумя
детекторами на одном и том же входе и synthetic calibration:

- `semantic_guard` — обязательный deterministic comparator;
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

На текущем 12-сценарном hard-generalization benchmark ни один из двух методов
не удовлетворяет всем требованиям deployable candidate: `semantic_guard`
теряет attack recall при строгом low-FPR threshold, а PA-TEF улучшает recall,
но scenario-disjoint FPR остаётся выше целевых 0,1%. Поэтому external controls
не должны заранее назначать один из них production-кандидатом.

## Критерий, при котором ML не оправдан

Если `semantic_guard` при равном или меньшем FPR стабильно имеет не худшие
Recall и detection delay на run-level, scenario-disjoint и leak-free ablation
оценках, learned fusion не имеет подтверждённого incremental value и не должен
позиционироваться как deployable преимущество.

## Freshness experiment

Hard-generalization benchmark показал, что короткий benign single-source
observer skew и свежая single-source divergence могут иметь одинаковый
semantic support. Новый optional provenance signal `*_age_steps` проверяет,
даёт ли явная freshness наблюдателя возможность снизить scenario-disjoint FPR
без потери attack recall.

Semantic guard намеренно не использует freshness. PA-TEF и generic ML-baselines
получают source-symmetric freshness features, а `no_freshness` ablation
показывает зависимость результата от дополнительного сенсора. Любой выигрыш
следует интерпретировать как результат **нового provenance assumption**, а не
как бесплатное улучшение классификатора.
