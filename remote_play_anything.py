import os
import requests
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

# This file is used to communicate information from this runtime into the steam invocation.
restart_file = Path.home() / 'remote_play_anything.txt'

steam_folder = None
app_data = {}
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

  with (steam_folder / 'appcache' / 'appinfo.vdf').open('rb') as f:
    bytes = f.read()

  import struct
  import re

  appid_regex = re.compile(rb"""
    (?P<appid>.{4})
    .{53} # Misc other stuff
    \x02appid\x00
    .*?
    \x01installdir\x00
    (?P<installdir>[^\x00]*)\x00
    .*?
    \x00depots\x00
  """, re.VERBOSE | re.DOTALL)

  executable_regex = re.compile(rb"""
    \x01executable\x00
    (?P<executable>[^\x00]*)\x00
    .*?
    \x01oslist\x00
    (?P<oslist>[^\x00]*)\x00
  """, re.VERBOSE)
  
  for m in appid_regex.finditer(bytes):
    appid = struct.unpack('I', m['appid'])[0]
    app_data[appid] = {
      'installdir': m['installdir'].decode('utf-8'),
      'executable': {}, # windows, macos, linux
    }
    for m in executable_regex.finditer(bytes, m.start(), m.end()):
      for os in m['oslist'].decode('utf-8').split(','):
        app_data[appid]['executable'][os] = m['executable'].decode('utf-8')


def open_url(url):
  if sys.platform == 'win32':
    subprocess.run(['cmd', '/c', 'start', url.replace('&', '^&')])
  elif sys.platform == 'darwin':
    os.system('open ' + url.replace('?', '\\?').replace('&', '\\&'))
  else:
    os.system('xdg-open ' + url)


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
  try:
    app_info = app_data[int(appid)]
  except KeyError:
    return None
  path = steam_folder / 'steamapps' / 'common' / app_info['installdir']
  if sys.platform == 'win32':
    path /= app_info['executable']['windows']
  elif sys.platform == 'darwin':
    path /= app_info['executable']['macos']
  else:
    path /= app_info['executable']['linux']
  return path


def get_steam_games():
  steam_games = []
  for file in steam_folder.glob('steamapps/appmanifest_*.acf'):
    game_data = {}
    with file.open('r', encoding='utf8') as f:
      for line in f:
        if '"appid"' in line:
          game_data['appid'] = line.split('"')[3]
        elif '"name"' in line:
          game_data['name'] = line.split('"')[3]
        elif '"installdir"' in line:
          game_data['installdir'] = line.split('"')[3]
    steam_games.append(game_data)
  return steam_games


# Search for an installed game which supports Remote Play Together
def get_rpt_enabled_game(steam_games):
  for game in steam_games:
    text = requests.get('https://store.steampowered.com/app/' + game['appid']).text
    if 'ico_remote_play_together.png' in text:
      route_target = get_primary_executable(game['appid'])
      if route_target and route_target.exists():
        return (route_target, game['appid'])

  # Else, no remote-play enabled apps are installed
  steam_f2p_rpt_games = 'https://store.steampowered.com/search/?maxprice=free&category2=44'
  if sys.platform == 'win32':
    steam_f2p_rpt_games += '&os=win'
  elif sys.platform == 'darwin':
    steam_f2p_rpt_games += '&os=mac'
  else:
    steam_f2p_rpt_games += '&os=linux'
  print('No available games support Steam Remote Play. Please go download a remote-play compatible game:\n' + steam_f2p_rpt_games)
  should_open = input('Open URL in Steam (Y/N): ')
  if should_open.lower()[0] == 'y':
    open_url('steam://openurl/' + steam_f2p_rpt_games)
  sys.exit(0)


def remote_play_anything():
  steam_games = get_steam_games()

  game_folders = [path for path in (steam_folder / 'steamapps' / 'common').iterdir() if path.is_dir()]
  game = show_chooser(game_folders, key=lambda p: p.stem)

  target = None
  for steam_game in steam_games:
    if game.stem == steam_game['installdir']:
      target = get_primary_executable(steam_game['appid'])
      break

  if not target:
    if sys.platform == 'win32':
      executables = list(game.glob('**/*.exe'))
    elif sys.platform == 'darwin':
      executables = list(game.glob('**/*.app'))
    else:
      executables = [] # Probably should be everything with the executable bit set.
    target = show_chooser(executables, key=lambda p: p.stem)

  with restart_file.open('w+') as f:
    f.write(str(target))

  # Real executable (which supports RPT)
  route_target, appid = get_rpt_enabled_game(steam_games)
  # Rename it while we inject ourselves
  renamed_target = route_target.parent / ('_' + route_target.name) 
  renamed_target.unlink(missing_ok=True) # In case we failed to clean up, somehow
  route_target.rename(renamed_target)
  shutil.copy(sys.executable, route_target)

  # Then instruct steam to open the target game (which it will do with RPT enabled)
  # We will relaunch and run the function run_target_executable
  open_url('steam://rungameid/' + appid)


def run_target_executable():
  with restart_file.open('r') as f:
    exe_path = Path(f.read()) # Path to the exectuable we want to launch in our stead
  # Remove restart file (since we have now restarted)
  restart_file.unlink()

  # Rerun as target process
  # TODO: Remove extraneous args?
  print(exe_path)
  subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent), stdin=None, stderr=None, close_fds=None)

  # Restore route target (involves deleting ourselves, so we need a bit of a hack)
  route_target = Path(sys.executable)
  route_target = str(route_target.parent / ('_' + route_target.name))

  if sys.platform == 'win32':
    os.system(f'cmd /c ping 127.0.0.1 -n 4 >nul & del {sys.executable} & move {route_target} {sys.executable}') 
  elif sys.platform == 'darwin':
    os.system('sleep 3; rm {sys.executable}; mv {route_target} {sys.executable}')
  else:
    os.system('sleep 3; rm {sys.executable}; mv {route_target} {sys.executable}')


if __name__ == '__main__':
  if restart_file.exists():
    run_target_executable()
  else:
    get_steam_folder()
    remote_play_anything()



