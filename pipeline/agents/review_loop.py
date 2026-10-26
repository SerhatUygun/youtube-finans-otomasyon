"""Editor / Denetleyici / Tester üçlü döngüsü -- genel amaçlı retry-with-feedback iskeleti.

Herhangi bir aşama (s05b motion graphics, s07 final edit, ileride s03/s05) kendi
Editor/render/Tester fonksiyonlarını verip bu döngüyü çağırır; döngünün kendisi hiçbir
render/LLM mantığı içermez, sadece üçünü sıraya koyar.

Akış: Editor(feedback) -> aday üretir -> Reviewer kritik eder (opsiyonel) -> onaylanırsa
render -> Tester doğrular -> ikisi de geçerse başarı; biri reddederse geri bildirimle
Editor'a dönülür (max_revisions kez). Tükenirse çağıran taraf mevcut güvenli davranışına
(örn. statik görsel / eski segment) düşer -- bu döngü ASLA üretimi durduran zorunlu bir
kapı değildir, sadece kaliteyi artıran opsiyonel bir katmandır."""
from pipeline.utils.logging import get_logger

log = get_logger("agents.review_loop")


def run_loop(propose_fn, render_fn, validate_fn, review_fn=None, max_revisions: int = 2) -> dict:
    """
    propose_fn(feedback: str | None) -> candidate dict | None
        Editor. feedback=None ilk deneme; sonraki denemelerde önceki reddin nedeni verilir.
        None dönerse Editor "pes etti" demektir, döngü hemen başarısız biter.
    render_fn(candidate) -> rendered_path | None
        Adayı gerçekten render eder. None/exception -> render başarısız sayılır.
    validate_fn(candidate, rendered_path) -> {"pass": bool, "checks": {...}, ...}
        Tester. render edilmiş çıktıyı teknik olarak doğrular.
    review_fn(candidate) -> {"approved": bool, "reason": str, "suggested_fix": str|None}
        Denetleyici (opsiyonel). Verilmezse bu adım atlanır (her aday direkt render edilir).

    Döner: {"success": bool, "candidate": dict|None, "rendered_path": Any|None,
            "attempts": int, "history": [ {"attempt", "stage", "result"}, ... ]}
    """
    feedback = None
    history = []

    for attempt in range(1, max_revisions + 2):  # ilk deneme + max_revisions revizyon
        try:
            candidate = propose_fn(feedback)
        except Exception as e:
            history.append({"attempt": attempt, "stage": "editor", "result": f"exception: {e}"})
            break
        if candidate is None:
            history.append({"attempt": attempt, "stage": "editor", "result": "no_candidate"})
            break

        if review_fn:
            try:
                verdict = review_fn(candidate)
            except Exception as e:
                verdict = {"approved": True, "reason": f"reviewer-exception: {e}"}
            history.append({"attempt": attempt, "stage": "reviewer", "result": verdict})
            if not verdict.get("approved", True):
                feedback = verdict.get("suggested_fix") or verdict.get("reason")
                log.info(f"Denetleyici reddetti (deneme {attempt}): {verdict.get('reason')}")
                continue

        try:
            rendered_path = render_fn(candidate)
        except Exception as e:
            rendered_path = None
            log.warning(f"Render sırasında hata (deneme {attempt}): {e}")
        if not rendered_path:
            history.append({"attempt": attempt, "stage": "render", "result": "failed"})
            feedback = "Render başarısız oldu, farklı/daha basit bir aday dene."
            continue

        try:
            test_result = validate_fn(candidate, rendered_path)
        except Exception as e:
            test_result = {"pass": False, "checks": {"tester_exception": str(e)}}
        history.append({"attempt": attempt, "stage": "tester", "result": test_result})
        if test_result.get("pass", False):
            return {"success": True, "candidate": candidate, "rendered_path": rendered_path,
                    "attempts": attempt, "history": history}

        feedback = f"Test başarısız: {test_result.get('checks')}"
        log.info(f"Tester reddetti (deneme {attempt}): {test_result.get('checks')}")

    return {"success": False, "candidate": None, "rendered_path": None,
            "attempts": len(history), "history": history}
