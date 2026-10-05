"""Native Textual → SVG → PNG/GIF. Fonts are referenced locally, never bundled."""
import io
from pathlib import Path
import re
import subprocess
import tempfile
from rich.console import Console
from rich._export_format import CONSOLE_SVG_FORMAT


def font():
    try:
        family=subprocess.check_output(['fc-match','Iosevka Term','-f','%{family}'],text=True)
        if 'Iosevka Term' in family:return 'Iosevka Term',.5
    except (OSError,subprocess.CalledProcessError):pass
    return 'monospace',.61


def svg(app):
    family,aspect=font()
    console=Console(width=app.size.width,height=app.size.height,file=io.StringIO(),force_terminal=True,
        color_system='truecolor',record=True,legacy_windows=False,safe_box=False)
    console.print(app.screen._compositor.render_update(full=True,screen_stack=app._background_screens))
    template=re.sub(r'@font-face\s*\{\{.*?\}\}', '', CONSOLE_SVG_FORMAT, flags=re.S)
    template=template.replace('Fira Code, monospace',f'"{family}", monospace')
    template=template.replace('{chrome}','<rect width="100%" height="100%" fill="#090b0b"/>')
    result=console.export_svg(title='',font_aspect_ratio=aspect,code_format=template)
    return result.replace('<svg ','<svg xml:space="preserve" ',1)


def png(source,destination):
    subprocess.run(['rsvg-convert','-w','1320','-o',str(destination),str(source)],check=True)


def screenshot(app,folder,name):
    path=folder/(name+'.svg');path.write_text(svg(app));png(path,path.with_suffix('.png'))


def gif(frames,destination):
    """Frames are actual rendered application states with explicit hold times."""
    with tempfile.TemporaryDirectory(prefix='thrash-frames-') as temp:
        root=Path(temp);lines=[]
        for i,(frame,duration) in enumerate(frames):
            source=root/f'{i:03}.svg';source.write_text(frame)
            image=source.with_suffix('.png');png(source,image)
            lines += [f"file '{image}'",f'duration {duration}']
        lines += [f"file '{image}'"]
        listing=root/'frames.txt';listing.write_text('\n'.join(lines)+'\n')
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(listing),
            '-filter_complex','fps=8,split[a][b];[a]palettegen=stats_mode=diff:max_colors=64[p];[b][p]paletteuse=dither=none',
            '-t',str(sum(duration for _,duration in frames)),'-loop','0',str(destination)],check=True)
