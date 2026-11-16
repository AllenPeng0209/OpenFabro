from test_workbench import client, draft


def test_recovery_can_distinguish_missing_editable_file_without_creating_it(client):
    made=draft(client);url=f"/api/workbench/projects/{made['id']}/text/docs/missing.md"
    assert client.get(url).status_code==404
    response=client.get(url,params={'allow_missing':'true'})
    assert response.status_code==200 and response.json()=={'exists':False,'content':'','sha':None}
    assert client.get(url).status_code==404


def test_missing_recovery_path_keeps_reserved_output_and_traversal_guards(client):
    made=draft(client)
    for path in ['mechanical/absent.json','native/absent.json','history/absent.json','references/canvas/absent.json','state.json']:
        assert client.get(f"/api/workbench/projects/{made['id']}/text/{path}",params={'allow_missing':'true'}).status_code==422
