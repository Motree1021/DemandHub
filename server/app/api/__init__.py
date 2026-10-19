from fastapi import APIRouter


def build_router(settings):
    from app.api import (
        admin,
        admin_channels,
        admin_dicts,
        admin_grants,
        admin_identities,
        admin_notify_templates,
        admin_orgs,
        admin_sla,
        admin_statemachine,
        admin_types,
        admin_users,
        admin_whitelist,
        agent,
        assist,
        auth,
        comment,
        dashboard,
        demand,
        effort,
        health,
        notification,
        relation,
        report,
        solution,
        standards,
        triage,
    )
    router = APIRouter(prefix=settings.api_root_path)
    for module in (health, auth, standards, demand, triage, solution, comment, effort,
                   relation, admin, admin_statemachine, admin_users, admin_grants,
                   admin_notify_templates, notification, dashboard, report, agent, assist):
        router.include_router(module.router)
    router.include_router(admin_dicts.router)
    router.include_router(admin_dicts.query_router)
    router.include_router(admin_types.router)
    router.include_router(admin_sla.router)
    router.include_router(admin_channels.router)
    router.include_router(admin_whitelist.router)
    router.include_router(admin_orgs.router)
    router.include_router(admin_identities.router)
    if settings.auth_dev_login:
        router.include_router(auth.dev_router)
    if settings.auth_test_login:
        router.include_router(auth.test_router)
    if settings.channel_entry_auth_mode == "trusted_parameters":
        router.include_router(auth.parameters_router)
    return router
