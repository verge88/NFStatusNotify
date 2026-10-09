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
