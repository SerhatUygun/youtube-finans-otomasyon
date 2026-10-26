import logging
import sys

_FORMATTER = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def get_logger(name: str) -> logging.Logger:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_FORMATTER)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def attach_job_log_file(job_id: str) -> None:
    """17 Eyl: bir işin TÜM aşama loglarını (log.info/warning/error, hangi modülden
    gelirse gelsin) output/<job_id>/_raw/pipeline.log dosyasına da yazar. Root logger'a
    eklenir -- her modülün get_logger(name) ile aldığı logger varsayılan olarak root'a
    propagate eder, o yüzden tek bir FileHandler tüm aşamaları kapsar.

    Bu OLMADAN: orchestrator.py'deki try/except'ler bir aşama başarısız olduğunda sadece
    stdout'a log.error basıyordu -- arka planda/detached çalışan bir iş için stdout hiç
    yakalanmazsa (bugün başımıza geldiği gibi) başarısızlığın nedeni tamamen kayboluyordu,
    hatayı bulmak için işi elle tekrar çalıştırmak gerekiyordu."""
    from pipeline.utils.paths import job_path

    root = logging.getLogger()
    log_path = job_path(job_id, "pipeline.log")
    for h in list(root.handlers):
        if isinstance(h, logging.FileHandler) and hasattr(h, "_job_log_path"):
            if h._job_log_path == str(log_path):
                return  # zaten ekli (aynı job_id ile iki kez çağrılırsa çift yazmayı önler)
            # 18 Eyl: BAŞKA bir job_id'nin handler'ı -- aynı Python sürecinde birden fazla
            # iş art arda işlenirse (ör. bir test scripti/agent döngüsü) eskisi kaldırılmazsa
            # HER iki job'ın logu birbirininkine de sızıyordu (kaynağı karıştırıyordu).
            root.removeHandler(h)
            h.close()
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(_FORMATTER)
    handler._job_log_path = str(log_path)  # yukarıdaki tekrar-kontrolü için
    root.addHandler(handler)
    root.setLevel(logging.INFO)
