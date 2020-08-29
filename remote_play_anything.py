import json
import requests
import shutil
import subprocess
import sys
from pathlib import Path

# This file is used to communicate information from this runtime until the next time we get called.
restart_file = Path('C:/Users/localhost/Desktop/foo.txt')

steam_folder = None
def get_steam_folder():
  global steam_folder
  if sys.platform == 'win32':
    import winreg
    steam_folder = 'C:/Program Files (x86)/Steam'
    try:
      (steam_folder, _) = winreg.QueryValue(winreg.HKEY_CURRENT_USER, 'SOFTWARE\Valve\Steam\SteamPath')
    except OSError:
      pass
    print('Determined steam folder: ' + steam_folder)
  else:
    steam_folder = input('Enter steam folder: ')

  steam_folder = Path(steam_folder)


def show_chooser(options, key=None):
  id = 0
  padSize = len(str(len(options))) # log would be smarter, but idgaf
  for option in options:
    option_text = key(option) if key else option
    print(str(id).rjust(padSize) + ': ' + option_text)
    id += 1
  choice = int(input('Select an option: '))
  return options[choice]

def get_route_target():
  steam_games = []
  found = False
  for file in steam_folder.glob('steamapps/appmanifest_*.acf'):
    game_data = {}
    with file.open('r', encoding='utf8') as f:
      for line in f:
        if '"appid"' in line:
          game_data['appid'] = line.split('"')[3]
        elif '"installdir"' in line:
          game_data['installdir'] = line.split('"')[3]

    text = requests.get('https://store.steampowered.com/app/' + game_data['appid']).text
    if 'https://store.steampowered.com/remoteplay_hub' in text:
      found = True
      break

  if not found:
    print('No routable games found') # Improve this error. This means "Go download a RPT game"

  route_folder = steam_folder / 'steamapps' / 'common' / game_data['installdir']
  # TODO: Non-windows is probably not 'exe'. Hmm.
  route_target = show_chooser(list(route_folder.glob('**/*.exe')), key=lambda p: p.stem)
  return (route_target, game_data['appid'])


def remote_play_anything():
  route_target, appid = get_route_target()

  game_folders = [path for path in (steam_folder / 'steamapps' / 'common').iterdir() if path.is_dir()]
  game = show_chooser(game_folders, key=lambda p: p.stem)

  # TODO: Non-windows is probably not 'exe'. Hmm.
  exe = show_chooser(list(game.glob('**/*.exe')), key=lambda p: p.stem)

  with restart_file.open('w+') as f:
    f.write(str(exe))

  target_path = str(route_target)
  route_target.rename(route_target.parent / ('_' + route_target.name))
  shutil.copy(sys.executable, target_path)

  if sys.platform == 'win32':
    subprocess.run(['cmd', '/c', 'start', 'steam://rungameid/' + appid])
  elif sys.platform == 'darwin':
    import os
    os.command('open steam://rungameid/' + appid)
  else:
    import os
    os.command('xdg-open steam://rungameid/' + appid)


if __name__ == '__main__':
  try:
    with restart_file.open('r') as f:
      path = Path(f.read())
    # Remove restart file (since we have now restarted)
    # restart_file.unlink()
    # Restore route target
    # Path(sys.executable).unlink()
    # Path('_' + sys.executable).rename(sys.executable)

    subprocess.Popen([str(path)], cwd=str(path.parent), stdin=None, stderr=None, close_fds=None)
    sys.exit(0)
  except FileNotFoundError:
    pass

  # TODO: Compare file timestamp to exe timestamp


  get_steam_folder()
  remote_play_anything()

