"""The transport is mocked, not the SDK's serialization/privacy boundary."""
import json
import socket
import pytest
from thrash import tracing as t

sdk = pytest.importorskip('sentry_sdk')
from sentry_sdk.transport import Transport

class MemoryTransport(Transport):
    def __init__(self, options):
        super().__init__(options)
        self.envelopes = []
    def capture_envelope(self, envelope):
        self.envelopes.append(envelope)

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('THRASH_SENTRY','1')
    monkeypatch.setenv('SENTRY_DSN','https://public@example.invalid/1')
    monkeypatch.setattr(t,'_client',None)
    real = sdk.Client
    monkeypatch.setattr(sdk,'Client',lambda **kw: real(transport=MemoryTransport, **kw))
    c=t._get_client()
    yield c
    c.close()

def events(client):
    return [item.payload.json for e in client.transport.envelopes for item in e.items]

@pytest.mark.parametrize('flag,dsn',[(None,None),('0','https://public@example.invalid/1'),('1',None)])
def test_disabled_has_no_network_or_sdk(monkeypatch,flag,dsn):
    monkeypatch.delenv('THRASH_SENTRY',raising=False);monkeypatch.delenv('SENTRY_DSN',raising=False)
    if flag is not None:monkeypatch.setenv('THRASH_SENTRY',flag)
    if dsn:monkeypatch.setenv('SENTRY_DSN',dsn)
    def fail(*a,**kw):raise AssertionError('unexpected SDK/network')
    monkeypatch.setattr(sdk,'Client',fail);monkeypatch.setattr(socket.socket,'connect',fail)
    assert t._get_client() is None
    with t.span('thrash.page_fault'):
        with t.span('thrash.gemma.resume'):pass

@pytest.mark.parametrize('key', ['path','alias','prompt','completion','irq_text','commit_message','source','env','user','notes'])
def test_private_content_never_reaches_transport(client,key):
    secret='PRIVATE-canary-/home/person/projects/real-name'
    with t.span('thrash.page_fault',**{key:secret}) as data:
        data[key]=secret
        with t.span('thrash.gemma.resume',**{key:secret,'inference_ms':123}):pass
    payload=events(client)
    assert payload, 'actual SDK transport must receive the trace'
    assert secret not in json.dumps(payload)
    assert 'inference_ms' in json.dumps(payload)
    assert 'server_name' not in json.dumps(payload)


def test_sdk_ambient_context_cannot_escape(client):
    sdk.set_user({'email':'PRIVATE-identity'})
    sdk.set_tag('project','PRIVATE-alias')
    try:
        with t.span('thrash.page_fault'):pass
        assert 'PRIVATE' not in json.dumps(events(client))
    finally:
        sdk.set_user(None)
        sdk.get_current_scope().remove_tag('project')


def test_metrics_are_typed_and_allowlisted():
    assert t.metrics({'duration_ms':'/private','schema_valid':'secret','alias':'private',
                      'inference_ms':float('nan'),'retry_count':2,'schema_valid':True,
                      'gen_ai.request.model':'private-model'}) == {'retry_count':2,'schema_valid':True}


def test_sanitizer_discards_sdk_context(client):
    with t.span('thrash.page_fault'):pass
    event=events(client)[0]
    event.update(user={'email':'PRIVATE'},request={'url':'PRIVATE'},extra={'env':'PRIVATE'},
                 server_name='PRIVATE',breadcrumbs=[{'message':'PRIVATE'}])
    assert 'PRIVATE' not in json.dumps(t.scrub_transaction(event))


def test_nested_structure_and_safe_metrics(client):
    with t.span('thrash.page_fault'):
        with t.span('thrash.gemma.resume',**{'gen_ai.request.model':'gemma3:4b',
                    'gen_ai.usage.input_tokens':42,'gen_ai.usage.output_tokens':12}):pass
    e=events(client)[0]
    assert e['contexts']['trace']['op']=='gen_ai.invoke_agent'
    s=e['spans'][0]
    assert s['op']=='gen_ai.request'
    assert s['parent_span_id']==e['contexts']['trace']['span_id']
    assert s['data']['gen_ai.usage.input_tokens']==42


def test_failure_does_not_change_business_exception(client,monkeypatch):
    def broken(*a,**kw):raise RuntimeError('private transport detail')
    monkeypatch.setattr(client,'capture_event',broken)
    with t.span('thrash.page_fault'):assert 2+2==4
    with pytest.raises(ValueError,match='original'):
        with t.span('thrash.page_fault'):raise ValueError('original')
    assert t._current.get() is None


def test_exception_text_never_sent(client):
    with pytest.raises(ValueError):
        with t.span('thrash.page_fault'):raise ValueError('PRIVATE exception source')
    e=events(client)[0]
    assert e['contexts']['trace']['data']['failed'] is True
    assert 'PRIVATE' not in json.dumps(e)


def test_restore_behavior_with_real_sdk(client,kernel3):
    result=kernel3.restore(kernel3.reg.resolve('alpha'))
    assert result.resume.available
    event=events(client)[-1]
    assert event['transaction']=='thrash.page_fault'
    assert {'thrash.process_image.load','thrash.drift.detect','thrash.restore.render'} <= {s['description'] for s in event['spans']}
    all_bytes=b''.join(e.serialize() for e in client.transport.envelopes)
    assert b'alpha' not in all_bytes
    assert str(kernel3.cfg.data_dir).encode() not in all_bytes


def test_optional_sdk_missing_or_invalid(monkeypatch):
    monkeypatch.setenv('THRASH_SENTRY','1');monkeypatch.setenv('SENTRY_DSN','bad')
    monkeypatch.setattr(t,'_client',None)
    assert t._get_client() is None
    with t.span('thrash.page_fault'):pass


def test_ollama_safe_counts_not_payload(client,cfg):
    import httpx
    from thrash.ollama_client import chat_json
    def respond(request):
        assert request.url.host=='127.0.0.1'
        return httpx.Response(200,json={'message':{'content':'PRIVATE completion'},
            'prompt_eval_count':42,'eval_count':11,'load_duration':1000000,'eval_duration':2000000})
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        with t.span('thrash.page_fault'):
            reply=chat_json(cfg,'PRIVATE prompt',[{'role':'user','content':'PRIVATE source'}],client=http)
    assert reply.text=='PRIVATE completion' and reply.input_tokens==42
    payload=json.dumps(events(client))
    assert 'PRIVATE' not in payload
    model=events(client)[0]['spans'][0]['data']
    assert model['model_load_ms']==1 and model['generation_ms']==2
    assert 'prompt_eval_ms' not in model


def test_absent_sdk_is_noop(monkeypatch):
    import builtins
    original=builtins.__import__
    def imports(name,*a,**kw):
        if name=='sentry_sdk':raise ImportError('optional dependency missing')
        return original(name,*a,**kw)
    monkeypatch.setattr(builtins,'__import__',imports)
    monkeypatch.setenv('THRASH_SENTRY','1');monkeypatch.setenv('SENTRY_DSN','https://public@example.invalid/1')
    monkeypatch.setattr(t,'_client',None)
    with t.span('thrash.page_fault'):pass
    assert t._client is None


def test_disabled_kernel_and_local_model_make_no_external_connections(monkeypatch,kernel3,cfg):
    import httpx
    from thrash.ollama_client import chat_json
    monkeypatch.delenv('THRASH_SENTRY',raising=False)
    monkeypatch.setenv('SENTRY_DSN','https://public@example.invalid/1')
    def forbidden(*a,**kw):raise AssertionError('external network attempted')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(sdk,'Client',forbidden)
    assert kernel3.restore(kernel3.reg.resolve('alpha')).resume.available
    def local(request):
        assert request.url.host in ('127.0.0.1','::1')
        return httpx.Response(200,json={'message':{'content':'{}'}})
    with httpx.Client(transport=httpx.MockTransport(local)) as http:
        assert chat_json(cfg,'system',[],client=http).text=='{}'
