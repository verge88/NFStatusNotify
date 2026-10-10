# NFStatusNotify Research Testbed

Воспроизводимый исследовательский стенд для проверки методов обнаружения
скрытого рассогласования распределённого состояния 5G Core после подмены
`NFStatusNotify`.

Стенд ориентирован на научный вопрос: даёт ли provenance-aware ML преимущество
перед детерминированными правилами и стандартным anomaly detection при
неполной наблюдаемости и легитимных переходных состояниях.

## Что моделируется

Синтетический SBA-сценарий поддерживает независимые представления:

- состояние UDM в NRF;
- локальное представление/кэш AUSF;
- фактическое направление маршрута к UDM;
- наблюдения о `NFStatusNotify` и подписке;
- контекст update/recovery;
- маски доступности каждого источника.

Сценарий `forged_notify` меняет только локальное состояние AUSF и маршрут,
оставляя NRF неизменным. Это воспроизводит исследуемый постэффект cache
poisoning, но не содержит эксплуатационного сетевого payload.

## Сравниваемые методы

- `rules` — базовый semantic-consistency baseline;
- `semantic_guard` — специализированный детерминированный baseline с тем же semantic transition guard, что и PA-TEF;
- `isolation_forest` — unsupervised baseline, обучение только на benign train;
- `provenance_aware` — ML baseline, использующий признаки рассогласования,
  маски доступности и provenance;
- `patef` — provenance-aware temporal evidence fusion: независимые evidence
  experts, availability gating и out-of-fold fusion. Его вклад оценивается
  отдельно относительно `semantic_guard`, чтобы не приписывать ML эффект
  доменным правилам.

Текущая provenance-aware модель — **исследовательская отправная точка**, а не
заявление о научной новизне. Новизну следует доказывать через новый метод
построения/калибровки оценки и воспроизводимые эксперименты.

## Быстрый запуск

Требуется Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
nfnotify-lab all --config configs/experiment.yaml --out artifacts
```

Результаты:

- `artifacts/observations.csv` — исходные временные наблюдения;
- `artifacts/features.csv` — признаки и маски provenance;
- `artifacts/metrics.csv` — FPR, Recall@target-FPR, detection delay;
- `artifacts/ablations.csv` — абляции независимых источников;
- `artifacts/scenario-holdout.csv` — результаты scenario-disjoint holdout;
- `artifacts/scenario-holdout-summary.csv` — агрегированная оценка
  generalization на невиденные сценарии.

Целевой FPR по умолчанию: `0.001` (0,1%).

## Экспериментальные сценарии

| Сценарий | Смысл |
| --- | --- |
| `stable` | стабильная штатная работа |
| `legit_update` | корректный NRF update → notify → route change |
| `delayed_notify` | легитимная задержка уведомления |
| `udm_recovery` | отказ и восстановление UDM |
| `forged_notify` | моделируемый постэффект forged notification |
| `forged_notify_missing` | атака при деградации notify-телеметрии |
| `legit_update_missing` | штатный переход при неполных свидетельствах |

## Научная гипотеза

Проверяемая гипотеза:

> При одинаковом фактическом FPR provenance-aware метод обнаруживает больше
> нарушений согласованности и/или раньше, чем жёсткие правила и Isolation
> Forest, особенно при выпадении одного из независимых источников.

Если эта гипотеза не подтверждается, механизм следует оставить в
детерминированном контуре, а Data Mining направить на другую задачу.

## Документация

- [Threat model и границы безопасности](docs/threat-model.md)
- [Экспериментальный протокол](docs/experiment-design.md)
- [PA-TEF detector](docs/patef-detector.md)
- [Scenario-disjoint evaluation](docs/scenario-holdout.md)
- [Replicated real Open5GS study](docs/replicated-real-study.md)
- [Publication robustness experiments](docs/publication-robustness.md)
- [Frozen 1/8 candidate validation](docs/frozen-candidate-validation.md)
- [Publication artifact freeze](docs/publication-freeze.md)
- [Related-work and novelty ledger](docs/related-work-ledger.md)
- [Контракт подключения Open5GS telemetry](adapters/open5gs/README.md)

## Интеграция с Open5GS

Репозиторий намеренно не содержит exploit-кода для отправки forged
`NFStatusNotify`. Для авторизованного изолированного стенда Open5GS нужно
экспортировать read-only телеметрию в семантическую схему из
`adapters/open5gs/README.md` и прогонять её через тот же feature/evaluation
pipeline.

Так эксперимент отделяет воспроизведение уязвимости от задачи обнаружения и
позволяет безопасно сравнивать методы на реальных трассах.
