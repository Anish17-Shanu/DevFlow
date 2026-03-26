from fastapi import Request


def get_execution_service(request: Request):
    return request.app.state.runtime.execution_service


def get_worker_manager(request: Request):
    return request.app.state.runtime.worker_manager


def get_queue(request: Request):
    return request.app.state.runtime.queue


def get_realtime(request: Request):
    return request.app.state.runtime.realtime
