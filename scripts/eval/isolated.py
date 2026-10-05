"""Linux bubblewrap runner: only loopback exists during the real Gemma evaluation.

Installed Ollama weights are mounted read-only. All writable state lives in a
fresh temporary directory. The user Ollama home is hidden, not read.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

if '--inside' in sys.argv:
    import httpx
    work=Path(sys.argv[-1])
    env={**os.environ,'OLLAMA_HOST':'127.0.0.1:11434','OLLAMA_MODELS':str(work/'models')}
    with (work/'server.log').open('w') as log:
        server=subprocess.Popen(['ollama','serve'],env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            with httpx.Client(trust_env=False,timeout=1) as client:
                for _ in range(100):
                    try:
                        if client.get('http://127.0.0.1:11434/api/tags').status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.1)
                else:raise RuntimeError('Local Ollama did not start')
            subprocess.run([sys.executable,str(Path(__file__).with_name('run.py')),
                            '--output',str(work/'results.json')],check=True)
        finally:
            server.terminate()
            try:server.wait(timeout=10)
            except subprocess.TimeoutExpired:server.kill();server.wait()
else:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=subprocess.run(['ollama','show','gemma3:4b','--modelfile'],capture_output=True,text=True,check=True)
    blob=next(line.removeprefix('FROM ').strip() for line in result.stdout.splitlines() if line.startswith('FROM /'))
    with tempfile.TemporaryDirectory(prefix='thrash-isolated-eval-') as name:
        work=Path(name);(work/'ollama-home').mkdir();(work/'models').mkdir()
        command=['bwrap','--unshare-net','--unshare-pid','--die-with-parent','--ro-bind','/','/',
            '--proc','/proc','--dev-bind','/dev','/dev','--bind','/tmp','/tmp',
            '--bind',str(work/'ollama-home'),str(Path.home()/'.ollama'),
            '--ro-bind',str(Path(blob).parent.parent),str(work/'models'),
            '--setenv','PYTHONDONTWRITEBYTECODE','1','--',sys.executable,str(Path(__file__).resolve()),'--inside',str(work)]
        subprocess.run(command,check=True,timeout=2400)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_bytes((work/'results.json').read_bytes())
