"""Concurrent first requests must share one live workspace and its project objects."""
import concurrent.futures
import threading
import time
from wholeboard import config,project,server

def test_concurrent_cold_requests_cannot_lose_new_projects_in_duplicate_workspace_instances(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'APP_DIR',tmp_path);monkeypatch.setattr(config,'CONFIG_FILE',tmp_path/'config.json');config.update({'projects_dir':str(tmp_path/'projects')})
    monkeypatch.setattr(server,'manager',None);real=project.Manager;start=threading.Barrier(6)
    def loading_workspace():
        # Model slow filesystem reads, retaining the real manager's load/create effects.
        time.sleep(.05)
        return real()
    monkeypatch.setattr(server,'Manager',loading_workspace)
    def request():start.wait();return server.mgr()
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:clients=list(pool.map(lambda _:request(),range(6)))
    made=clients[0].create('A project created by the first client')
    assert all(client.get(made.id) is made for client in clients),'Concurrent requests used different workspaces and lost the new project'
    assert server.mgr().get(made.id) is made
