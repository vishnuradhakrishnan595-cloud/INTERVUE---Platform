from .models import AuditLog


def get_client_ip(request):
    if request is None:
        return None

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")

    return (
        forwarded_for.split(",")[0].strip()
        if forwarded_for
        else request.META.get("REMOTE_ADDR")
    )


def log_action(
    request,
    action,
    entity="",
    entity_id="",
    meta=None,
    user=None,
    company=None,
):
    # Use the explicitly supplied user, or fall back to the request user.
    user = user or getattr(request, "user", None)

    # Avoid assigning anonymous users to the audit log.
    if user is not None and not user.is_authenticated:
        user = None

    # Use the explicitly supplied company when available.
    # Otherwise, use the authenticated user's company.
    if company is None and user is not None:
        company = getattr(user, "company", None)

    AuditLog.objects.create(
        user=user,
        company=company,
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        meta=meta or {},
        ip_address=get_client_ip(request),
    )