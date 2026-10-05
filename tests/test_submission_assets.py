"""Public media must stay local-font-only and contain no runtime identities."""
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]

def test_public_hero_provenance_is_in_docs_not_watermarks():
    assets=list((ROOT/'docs/media').glob('0[1-7]-*.svg'))
    assert len(assets)==7
    for path in assets:
        raw=path.read_text()
        assert 'SYNTHETIC' not in raw
        assert '/home/' not in raw and '/tmp/' not in raw
        assert '@font-face' not in raw and 'url(' not in raw.replace('url(#','')
        assert 'Fira Code' in raw or 'monospace' in raw
    text=''.join(ET.fromstring((ROOT/'docs/media/02-page-fault.svg').read_text()).itertext())
    assert text.count('NEXT\u00a0EXECUTION')==1
    assert 'FAULT\u00a0RESOLVED' in text
