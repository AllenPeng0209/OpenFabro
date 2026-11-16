"""Automatic document excerpts must disclose omissions and support exact continuation."""
import copy
import hashlib
import json
import pytest

from test_workbench import client, draft
from wholeboard import server,codex_bridge


def project(client):
    return server.mgr().get(draft(client)['id'])


def context(p):
    prompt=codex_bridge.prompt_for(p,'Review the project documents','chat')
    return json.loads(prompt.split('PROJECT CONTEXT (reference data):\n',1)[1].split('\n\nUSER REQUEST:',1)[0])


def test_unicode_document_excerpt_discloses_its_full_identity_and_unseen_tail(client):
    p=project(client);path=p.root/'requirements.md';text='界'*12001+'\nUNSEEN_TAIL_REQUIREMENT';path.write_text(text)
    row=context(p)['documents'][0]
    assert row['truncated'] is True,'The model was not told that the document was incomplete'
    assert row['characters']==12025 and row['bytes']==36027
    assert row['offset']==0 and row['next_offset']==12000 and row['content']=='界'*12000
    assert row['sha256']==hashlib.sha256(text.encode()).hexdigest()
    tail=codex_bridge.execute_tool(p,'read_file',{'path':row['path'],'offset':row['next_offset'],'limit':20000,'expected_sha256':row['sha256']},'chat')
    assert row['content']+tail['content']==text and tail['truncated'] is False


def test_document_index_keeps_omitted_documents_discoverable_without_mutating_design(client):
    p=project(client);before=copy.deepcopy(p.state['spec']);docs=p.root/'docs';docs.mkdir()
    for i in range(13):(docs/f'{i:02}.md').write_text(f'Requirement {i}')
    data=context(p);coverage=data['documents_coverage']
    assert coverage['total']==13 and coverage['included']==12 and coverage['omitted']==1
    assert coverage['omitted_paths']==['docs/12.md'] and not coverage['content_complete']
    page=codex_bridge.execute_tool(p,'list_documents',{'offset':12,'limit':10,'expected_index_sha256':coverage['index_sha256']},'chat')
    assert [row['path'] for row in page['documents']]==['docs/12.md'] and page['next_offset']==13 and not page['truncated']
    assert p.state['spec']==before and p.state['workbench']['version']==1


def test_document_discovery_is_complete_beyond_the_bounded_omitted_path_preview(client):
    p=project(client);docs=p.root/'docs';docs.mkdir()
    for i in range(253):(docs/f'{i:03}.md').write_text(str(i))
    data=context(p);coverage=data['documents_coverage'];seen=[row['path'] for row in data['documents']]+coverage['omitted_paths']
    assert coverage['omitted_paths_truncated'] and len(seen)<253
    offset=coverage['omitted_next_offset']
    while offset<coverage['total']:
        result=codex_bridge.execute_tool(p,'list_documents',{'offset':offset,'limit':100,'expected_index_sha256':coverage['index_sha256']},'chat')
        seen.extend(row['path'] for row in result['documents']);assert result['next_offset']>offset;offset=result['next_offset']
    assert len(seen)==len(set(seen))==253 and set(seen)=={f'docs/{i:03}.md' for i in range(253)}


def test_file_hash_pinning_rejects_a_tail_from_a_different_saved_document(client):
    p=project(client);path=p.root/'requirements.md';path.write_text('Old requirements')
    initial=codex_bridge.execute_tool(p,'read_file',{'path':'requirements.md','limit':3},'chat')
    path.write_text('New requirements')
    with pytest.raises(ValueError,match='changed'):
        codex_bridge.execute_tool(p,'read_file',{'path':'requirements.md','offset':3,'expected_sha256':initial['sha256']},'chat')


def test_large_unicode_documents_use_character_offsets_and_are_readable_in_bounded_chunks(client):
    p=project(client);text='物'*80000+'TAIL';(p.root/'large.md').write_text(text)
    result=codex_bridge.execute_tool(p,'read_file',{'path':'large.md','offset':80000,'limit':10,'expected_sha256':hashlib.sha256(text.encode()).hexdigest()},'chat')
    assert result['content']=='TAIL' and result['characters']==80004 and result['bytes']==240004
    assert not result['truncated'] and result['next_offset']==80004


def test_document_context_does_not_expose_hidden_or_symlinked_files(client):
    p=project(client);outside=p.root.parent.parent/'outside.md';outside.write_text('SECRET_MARKER')
    (p.root/'linked.md').symlink_to(outside);(p.root/'linked_directory').symlink_to(outside.parent,target_is_directory=True)
    hidden=p.root/'.hidden';hidden.mkdir();(hidden/'notes.md').write_text('SECRET_MARKER')
    (p.root/'visible.MD').write_text('Visible requirement')
    data=context(p);assert [d['path'] for d in data['documents']]==['visible.MD']
    listing=codex_bridge.execute_tool(p,'list_documents',{},'chat')
    assert listing['total']==1 and 'SECRET_MARKER' not in json.dumps(data)+json.dumps(listing)


def test_changed_document_index_cannot_silently_skip_a_file_during_pagination(client):
    p=project(client);(p.root/'b.md').write_text('B');first=codex_bridge.execute_tool(p,'list_documents',{'limit':1},'chat')
    (p.root/'a.md').write_text('A')
    with pytest.raises(ValueError,match='changed'):
        codex_bridge.execute_tool(p,'list_documents',{'offset':1,'expected_index_sha256':first['index_sha256']},'chat')


def test_invalid_utf8_document_is_disclosed_as_unread_instead_of_silently_replaced(client):
    p=project(client);(p.root/'broken.md').write_bytes(b'\xff\xfe')
    data=context(p);row=data['documents'][0]
    assert row['read_error'] and row['content']=='' and row['characters'] is None
    assert row['sha256']==hashlib.sha256(b'\xff\xfe').hexdigest()
    assert data['documents_coverage']['failed']==1 and not data['documents_coverage']['content_complete']


def test_oversized_document_is_explicitly_unavailable_and_read_file_stays_bounded(client):
    p=project(client);(p.root/'oversized.md').write_bytes(b'x'*2_000_001)
    data=context(p);row=data['documents'][0]
    assert row['read_error'] and row['bytes']==2_000_001 and not row['content']
    assert not data['documents_coverage']['content_complete']
    with pytest.raises(ValueError,match='2 MB'):
        codex_bridge.execute_tool(p,'read_file',{'path':'oversized.md'},'chat')


@pytest.mark.parametrize('arguments',[{'offset':True},{'offset':-1},{'limit':0},{'limit':101}])
def test_document_index_rejects_invalid_pagination(arguments,client):
    with pytest.raises(ValueError,match='offset|limit'):
        codex_bridge.execute_tool(project(client),'list_documents',arguments,'chat')


@pytest.mark.parametrize('expected',['bad',True,[]])
def test_read_file_rejects_invalid_snapshot_hashes(expected,client):
    p=project(client);(p.root/'readme.md').write_text('Text')
    with pytest.raises(ValueError,match='SHA'):
        codex_bridge.execute_tool(p,'read_file',{'path':'readme.md','expected_sha256':expected},'chat')
