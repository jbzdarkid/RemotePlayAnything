import os
import requests
import shutil
import subprocess
import sys
from pathlib import Path

# This file is used to communicate information from this runtime into the steam invocation.
restart_file = Path.home() / 'remote_play_anywhere.txt'

steam_folder = None
def get_steam_folder():
  global steam_folder
  if sys.platform == 'win32':
    import winreg
    try:
      (steam_folder, _) = winreg.QueryValue(winreg.HKEY_CURRENT_USER, 'SOFTWARE\Valve\Steam\SteamPath')
      steam_folder = Path(steam_folder)
    except OSError:
      steam_folder = Path('C:/Program Files (x86)') / 'Steam'
  elif sys.platform == 'darwin':
    steam_folder = Path.home() / 'Library' / 'Application Support' / 'Steam'
  else:
    steam_folder = Path(input('Enter steam folder: '))
  print('Determined steam folder: ' + str(steam_folder))


def open_url(url):
  if sys.platform == 'win32':
    subprocess.run(['cmd', '/c', 'start', url])
  elif sys.platform == 'darwin':
    os.command('open steam://rungameid/' + url)
  else:
    os.command('xdg-open ' + url)


def show_chooser(options, key=None):
  id = 0
  padSize = len(str(len(options))) # log would be smarter, but idgaf
  for option in options:
    option_text = key(option) if key else option
    print(str(id).rjust(padSize) + ': ' + option_text)
    id += 1
  choice = int(input('Select an option: '))
  return options[choice]

def get_primary_executable(appid):
  with (steam_folder / 'appcache' / 'appinfo.vdf').open('rb') as f:
    # TODO: Look at https://github.com/SteamDatabase/SteamAppInfo


# Search for an installed game which supports Remote Play Together
def get_rpt_enabled_appid():
  for file in steam_folder.glob('steamapps/appmanifest_*.acf'):
    appid = None
    with file.open('r', encoding='utf8') as f:
      for line in f:
        if '"appid"' in line:
          appid = line.split('"')[3]
          break

    text = requests.get('https://store.steampowered.com/app/' + appid).text
    if 'https://store.steampowered.com/remoteplay_hub' in text:
      return appid

  # Else, no remote-play enabled apps are installed
  steam_f2p_rpt_games = 'https://store.steampowered.com/search/?maxprice=free&category2=44'
  if sys.platform == 'win32':
    steam_f2p_rpt_games ++ '&os=win'
  elif sys.platform == 'darwin':
    steam_f2p_rpt_games ++ '&os=mac'
  else:
    steam_f2p_rpt_games ++ '&os=linux'
  print('No available games support Steam Remote Play. Please go download a remote-play compatible game: ' + steam_f2p_rpt_games)
  should_open = input('Open URL in Steam: Y/N')
  if should_open == 'Y':
    open_url('steam://openurl/' + steam_f2p_rpt_games)
  sys.exit(0)



def remote_play_anything():
  appid = get_rpt_enabled_appid()
  route_target = get_primary_executable(appid)

  game_folders = [path for path in (steam_folder / 'steamapps' / 'common').iterdir() if path.is_dir()]
  game = show_chooser(game_folders, key=lambda p: p.stem)

  # TODO: Non-windows is probably not 'exe'. Hmm.
  exe = show_chooser(list(game.glob('**/*.exe')), key=lambda p: p.stem)

  with restart_file.open('w+') as f:
    f.write(str(exe))

  target_path = str(route_target)
  route_target.rename(route_target.parent / ('_' + route_target.name))
  shutil.copy(sys.executable, target_path)

  open_url('steam://rungameid/' + appid)


def run_target_executable():
  with restart_file.open('r') as f:
    exe_path = Path(f.read()) # Path to the exectuable we want to launch in our stead
  # Remove restart file (since we have now restarted)
  restart_file.unlink()

  # Rerun as target process
  # TODO: Remove extraneous args?
  # subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent), stdin=None, stderr=None, close_fds=None)

  # Restore route target (involves deleting ourselves, so we need a bit of a hack)
  route_target = Path(sys.executable)
  route_target = str(route_target.parent / '_' + route_target.stem)
  print(route_target)
  input()
  if sys.platform == 'win32':
    os.command(f'cmd /c ping 127.0.0.1 -n 4 >nul & del {sys.executable} & move {route_target} {sys.executable}') 
  elif sys.platform == 'darwin':
    os.command('sleep 3; rm {sys.executable}; mv {route_target} {sys.executable}')
  else:
    os.command('sleep 3; rm {sys.executable}; mv {route_target} {sys.executable}')
    

def check_for_recompile():
  if Path(__file__).stat().st_mtime > Path(sys.executable).stat().st_mtime:
    print('File has been modified more recently than executable, please recompile')
    # sys.exit(0)


if __name__ == '__main__':
  # TODO: Maybe safer: Also check if calling process is named Steam.exe
  if restart_file.exists():
    run_target_executable()
  else:
    check_for_recompile() # Only while in development
    get_steam_folder()
    remote_play_anything()



