import copy
import pytest
from fastapi import HTTPException
from wholeboard import config,project,collaboration,modules
from test_module_updates import source,published,target
try:
    from wholeboard import module_catalog
except ImportError:
    module_catalog=None

@pytest.fixture
def workspace(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'APP_DIR',tmp_path);monkeypatch.setattr(config,'CONFIG_FILE',tmp_path/'config.json');config.update({'projects_dir':str(tmp_path/'projects')})
    manager=project.Manager();p=manager.create('Module source');p.state.update(spec=source(),owner_id='author',workbench={'version':1});p.save();return manager,p

def publish(p,asset,expected=0):
    assert module_catalog is not None,'The versioned workspace module catalog is missing'
    return module_catalog.publish(p,'Supply',asset,base_version=p.state['workbench']['version'],expected_version=expected)

def test_catalog_releases_are_immutable_and_persist_without_changing_the_source_design(workspace):
    manager,p=workspace;before=copy.deepcopy(p.state['spec']);v1=publish(p,published());assert v1['version']==1
    p.state['spec']['components'][1]['value']='2k';p.state['workbench']['version']=2;p.save();v2=publish(p,published(p.state['spec']),expected=1)
    assert v2['version']==2;actor={'id':'author','mode':'account','admin':False}
    old=module_catalog.resolve(manager,actor,v2['origin']['catalog_id'],version=1)
    assert old['design']['components'][1]['value']=='1k';assert p.state['spec']['components'][0]==before['components'][0]
    assert p.state['workbench']['version']==2
    assert module_catalog.resolve(manager,actor,v2['origin']['catalog_id'])['design']['components'][1]['value']=='2k'

def test_source_permissions_control_catalog_discovery_and_update_content(workspace):
    manager,p=workspace;asset=publish(p,published());viewer={'id':'viewer','mode':'account','admin':False}
    assert module_catalog.listing(manager,viewer)==[]
    with pytest.raises(HTTPException):module_catalog.resolve(manager,viewer,asset['origin']['catalog_id'])
    with collaboration.database() as db:db.execute('INSERT INTO members(project_id,user_id,role) VALUES(?,?,?)',(p.id,'viewer','viewer'))
    assert len(module_catalog.listing(manager,viewer))==1
    with collaboration.database() as db:db.execute('DELETE FROM members WHERE project_id=?',(p.id,))
    assert module_catalog.listing(manager,viewer)==[]

def test_stale_publish_or_invalid_catalog_path_cannot_replace_a_release(workspace):
    manager,p=workspace;asset=publish(p,published());changed=source();changed['components'][0]['value']='2k'
    with pytest.raises(HTTPException) as stale:publish(p,published(changed),expected=0)
    assert stale.value.status_code==409
    with pytest.raises(HTTPException):module_catalog.resolve(manager,{'id':'author','mode':'account','admin':False},'../config')
    assert module_catalog.resolve(manager,{'id':'author','mode':'account','admin':False},asset['origin']['catalog_id'])['version']==1

def test_historical_releases_keep_their_original_source_version(workspace):
    manager,p=workspace;v1=publish(p,published());p.state['spec']['components'][1]['value']='2k';p.state['workbench']['version']=2;p.save();v2=publish(p,published(p.state['spec']),expected=1)
    old=module_catalog.resolve(manager,{'id':'author','mode':'account','admin':False},v2['origin']['catalog_id'],version=1);assert old['origin']==v1['origin']
    with pytest.raises(ValueError):module_catalog.resolve(manager,{'id':'author','mode':'account','admin':False},v2['origin']['catalog_id'],version=True)

def test_catalog_origins_are_scoped_to_the_workspace(workspace):
    manager,p=workspace;asset=publish(p,published());assert asset['origin'].get('workspace')
    host=target();host['library']['modules']['Supply']=copy.deepcopy(asset);host['library']['modules']['Supply']['origin']['workspace']='another-workspace';host['library']['modules']['Supply']['version']=2
    rows=module_catalog.updates(manager,{'id':'author','mode':'account','admin':False},host);assert rows[0]['catalog_id'] is None
