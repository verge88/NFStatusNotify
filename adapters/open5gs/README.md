# Open5GS telemetry adapter contract

Этот каталог задаёт безопасную границу между реальным лабораторным Open5GS и
ML-пайплайном. Репозиторий не отправляет exploit traffic и не реализует
forged `NFStatusNotify`.

Для авторизованного изолированного стенда экспортируйте временные наблюдения
в таблицу с теми же семантическими полями, что генерирует
`nfnotify_lab.simulator`:

- `run_id`, `t`;
- `nrf_endpoint` — UDM endpoint по состоянию NRF;
- `ausf_endpoint` — локально используемый AUSF endpoint/кэш;
- `route_endpoint` — фактическое назначение исходящего SBI запроса;
- `nrf_update_seen`;
- `notify_seen`, `notify_subscription_valid`, `notify_sender_trusted`;
- `recovery_active`;
- `m_nrf`, `m_ausf`, `m_route`, `m_notify`;
- опционально `nrf_age_steps`, `ausf_age_steps`, `route_age_steps` —
  число sampling-интервалов с момента последнего подтверждённого обновления
  наблюдения источника; `0` означает свежую выборку, пустое/NaN — freshness
  неизвестна;
- `attack_start` и `attack_active` — только ground truth эксперимента.

Рекомендуемые безопасные точки наблюдения:

1. NRF API/журнал в read-only режиме;
2. инструментированный AUSF build или локальный диагностический hook;
3. service-mesh/eBPF/pcap наблюдение направления запросов в изолированном
   сегменте;
4. журнал SBI notifications;
5. оркестратор сценария, который пишет ground truth отдельно от telemetry.

Важно: `attack_start` не должен попадать в feature pipeline как признак.
Он используется только для оценки задержки обнаружения.

## Freshness provenance

Age-поля относятся к **свидетельству наблюдателя**, а не к возрасту самого
NF state. Например, live NRF discovery и pcap route для текущего probe имеют
age=0, а AUSF cache, реконструированный по последнему cache-event в журнале,
может иметь age>0, если после события не было нового подтверждения.

Пайплайн сохраняет неизвестную freshness как NaN и отдельно считает
`freshness_coverage`. Неизвестный возраст не интерпретируется как свежий.
