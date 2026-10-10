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


## Реально наблюдаемые времена источников (stage 5, experimental)

В штатной лаборатории `scripts/open5gs_failover_lab.py` каждый auth-probe
сопровождается **отдельным read-only NRF discovery**. Записывается
`nrf-observer-polls.jsonl` с ключом `(run_id,t)` и полями:

- `registered_udm_endpoints`, `expected_endpoint`, `poll_error` — реальный ответ
  NRF и отдельно контрольное ожидаемое состояние;
- `poll_start_epoch`, `poll_end_epoch` — границы получения NRF ответа;
- `probe_start_epoch`, `probe_end_epoch` — границы самостоятельного AUSF auth probe;
- `provenance_attested=false` — криптографически доверенных source-origin
  timestamps нет.

Отдельная команда `scripts/real_source_provenance_audit.py` формирует
`real-provenance-audit/source-time-audit.csv` и
`real-provenance-audit/source-time-decision.json`: сопоставляет
NRF-поллы, прошедшие AUSF cache setup events с временем журнала, и реальные
`generate-auth-data` pcap кадры **внутри интервала соответствующего
probe**. Пакеты из будущего не подтверждают текущую строку.

Важное различие времён:

- `nrf_origin_epoch`: **время завершения чтения NRF**, а не момент, когда
  UDM впервые был зарегистрирован;
- `ausf_origin_epoch`: дата **события изменения кэша** из журнала, а не
  непрерывно подтверждённое время актуальности кэша;
- `route_origin_epoch`: timestamp **захвата пакета pcap**, а не начало
  сетевого маршрута;
- `recovery_active`: разметка действий стенда, **не** доверенное
  свидетельство recovery внутри живого 5G Core;
- `notification_subscription_attested=0`: корректный адрес NRF в pcap
  **не доказывает** подлинность и авторизацию NFStatusNotify.

Исходные CSV для `ingest` и отдельный offline-counterfactual не получают
новые «доверенные» признаки. В текущем состоянии аудит нельзя применять для
автоматического блокирования или снятия тревог в реальной сети. Для этого
необходима отдельно верифицированная source-time телеметрия и проверка
устойчивости к атакующему, способному влиять на состояние восстановления.
