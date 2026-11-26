from aiogram import Router
from . import start, status, online, inbound, nodes, clients, client_portal, hosts


def get_main_router() -> Router:
    main_router = Router()
    main_router.include_router(start.router)
    main_router.include_router(client_portal.router)
    main_router.include_router(status.router)
    main_router.include_router(online.router)
    main_router.include_router(inbound.router)
    main_router.include_router(nodes.router)
    main_router.include_router(clients.router)
    main_router.include_router(hosts.router)
    return main_router
