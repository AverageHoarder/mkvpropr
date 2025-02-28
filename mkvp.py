import os
import subprocess
import re
import sys
import shutil
import getpass
from pathlib import Path
import xml.etree.ElementTree as ET
import argparse
from tqdm import tqdm
import yaml
import json
from time import sleep

def parse_arguments():
    def dir_path(path):
        if os.path.isdir(path) and path != None:
            return path
        else:
            raise argparse.ArgumentTypeError(f"readable_dir:{path} is not a valid path")
    
    parser = argparse.ArgumentParser(description='Scan for .mkv and .nfo files in subdirectories and set file title, track names, languages and flags.')
    parser.add_argument('-d', '--directory',
                        help='The directory that will be recursively scanned for .mkv and .nfo files.', type=dir_path, default=".", const=".", nargs="?")
    parser.add_argument('-s', '--single_folder', action='store_true',
                        help='Only scan the current folder for .mkv and .nfo files, no subdirectories.')
    parser.add_argument('--no_subformat', action='store_true',
                        help='Don\'t append Sub formats " (SRT)" etc. to the subtitle track names.')
    parser.add_argument('--no_renaming', action='store_true',
                        help='Don\'t rename .mkv files to match .nfo files and don\'t trim " (1)" etc. from .mkv names')
    parser.add_argument('--no_auto_flags', action='store_true',
                        help='When using "-" to skip a track, don\'t add forced/hearing impaired/commentary flags based on the track name')

    args: argparse.Namespace = parser.parse_args()

    return args

################################################### CONFIG ###################################################

# Directory in which the script will look for additional needed files
script_directory = Path(__file__).parent

with open(os.path.join(script_directory, "mkvp_config.yaml"), "r", encoding="utf8") as f:
    config = yaml.safe_load(f)

# Dictionary of language codes
langs = config["langs"]

# Automatically set forced, commentary and SDH flags based on existing track names when using "-" to skip
auto_set_flags_cfg = config["auto_set_flags"]

# Regex to match in track name to set track as forced
pattern_forced = re.compile(config["pattern_forced"]) if config["pattern_forced"] != "" else re.compile(r'(?i)\bforced\b')

# Regex to match in track name to set track as SDH
pattern_sdh = re.compile(config["pattern_sdh"]) if config["pattern_sdh"] != "" else re.compile(r'(?i)\b(?:SDH|CC)\b')

# Regex to match in track name to set track as commentary
pattern_commentary = re.compile(config["pattern_commentary"]) if config["pattern_commentary"] != "" else re.compile(r'(?i)\bcommentary\b')

# Language codes that get a "forced" flag
forced_langs = config["forced_langs"]

# Language codes that get a "hearing impaired" flag
sdh_langs = config["sdh_langs"]

# Language codes that get a "commentary" flag
comm_langs = config["comm_langs"]

# Directories that will not be scanned for .mkv and .nfo files
ignore_dirs = config["ignore_dirs"]

# .nfo names that will be ignored
ignore_nfos = config["ignore_nfos"]

# Append the subtitle format, can be overwritten with --no_subformat
add_sub_format_cfg = config["add_sub_format"]

# subformat codecs to display in the program and append to subtitle track names
sub_codec_replacements = config["sub_codec_replacements"]

# Rename .mkv files to match .nfo files and trim " (1)" etc. from .mkv names
rename_mkvs_cfg = config["rename_mkvs"]

# Regex to match and ignore unwanted .mkv files like trailers, samples..
pattern_unwanted = re.compile(config["pattern_unwanted"]) if config["pattern_unwanted"] != "" else re.compile(r'^.*-trailer.mkv$|^.*-sample.mkv$')

# Regex to match your tv-show file naming scheme and extract the episode title (only used when no matching .nfo is found)
if config["pattern_tvshow"] != "":
    pattern_tvshow = re.compile(config["pattern_tvshow"])
else:
    pattern_tvshow = re.compile(r'^.*\(\d{4}\)\s-\s\S\d{2,4}E\d{2,3}(?:\sS\d{2}E\d{2,3})*\s-\s([^[]+)\s\[.*\](?:\s\(\d\))?\.mkv$')

# Regex to match your movie file naming scheme and extract the movie title (only used when no matching .nfo is found)
pattern_movie = re.compile(config["pattern_movie"]) if config["pattern_movie"] != "" else re.compile(r'^(.*)\s\(\d{4}\)\s.*\.mkv$')

# regular expression to check if the format is already appended to the track name
pattern_sub = re.compile(config["pattern_sub"]) if config["pattern_sub"] != "" else re.compile(r'^(.*) (?:\(?SRT\)?|\(?ASS\)?|\(?VOB\)?|\(?PGS\)?)$')
                
# Width of the horizontal separator bar
h_bar = "─"*100

# Global counter to see how many .mkvs were renamed
mkvs_renamed = 0

# Global counter to see how many .mkv files were edited
mkvs_edited = 0

################################################## FUNCTIONS ##################################################

def mkv_tools_on_path():
    if not shutil.which("mkvmerge") or not shutil.which("mkvpropedit") and sys.platform == "win32":
        choice = input("mkvmerge or mkvpropedit executable is not on PATH, open environment variable settings in Windows to add them? (y/n): ")
        if choice == "y":
            print(f"""
    Step 1: Under 'User variables for {getpass.getuser()}' select 'Path' and either double click it or click on 'Edit...'
    Step 2: Click on 'New' and paste the path to the folder on your system that contains mkvmerge.exe and mkvpropedit.exe.
            Then confirm with "OK" twice.

            Info:
            If you do not have MKVToolNix installed yet, visit this website, download and install it:
            https://mkvtoolnix.download/downloads.html#windows
            If you chose a portable installation, you can pretty much put the folder wherever you like.
            My (non portable install) executables (as of writing) for example are located in
            C:\\Program Files\\MKVToolNix\\mkvmerge.exe
            C:\\Program Files\\MKVToolNix\\mkvpropedit.exe
            Once you have decided on where to store the portable version, add that path to PATH as described above.

            Note:
            You can also add the folder that contains this script to PATH in the same way
            if you want to call it from any folder.

    Step 3: Once that is done, re-run this script.""")
            try:
                subprocess.run(["rundll32.exe", "sysdm.cpl,EditEnvironmentVariables"])
            except subprocess.CalledProcessError:
                print(f"Error opening environment variable settings.")
            sys.exit()
        else:
            print("Exiting.")
            sys.exit()
    elif not shutil.which("mkvmerge") or not shutil.which("mkvpropedit"):
        print("mkvmerge/mkvpropedit not on PATH, add them and try again.")
        sys.exit()
    else:
        return

# Get the audio, subtitle and default-track info from the user
def getInput(mkv_files, movies_in_cat, category_count):
    # Validate inputs and requery in case of mistakes
    pattern_input = re.compile(r'^(?: *(\w{2,5}) *| *(-) *),(?: +([\w\d]{2,5}) *| +(-) *)+,(?: +([\w\d]{2,5}) *| *(-) *)* *$') # Audio codes are mandatory, subtitle codes optional
    testmovie = movies_in_cat[0]
    group_filecount = len(movies_in_cat)
    video_track_count = len(mkv_files[testmovie]["video"]) if "video" in mkv_files[testmovie] else 0
    audio_track_count = len(mkv_files[testmovie]["audio"]) if "audio" in mkv_files[testmovie] else 0
    subtitle_track_count = len(mkv_files[testmovie]["subtitles"]) if "subtitles" in mkv_files[testmovie] else 0
    while True:
        print()
        print(h_bar)
        print(os.path.basename(testmovie)[:100])
        print(h_bar)
        track_info = mkv_files[testmovie]
        for tracktype, tracks in track_info.items():
            if tracktype == "video":
                # print("Video:")
                for track in tracks:
                    id = track["id"]
                    lang = track["lang"]
                    name = track["name"]
                    codec = track["codec"]
                    print(f"{id:2} | {lang:^5} | {name[:40]:40} | {codec:20}")
                print(h_bar)
            elif tracktype =="audio":
                # print("Audio:")
                for track in tracks:
                    id = track["id"]
                    lang = track["lang"]
                    name = track["name"]
                    codec = track["codec"]
                    default = "Default" if track["default"] else ""
                    comm = "Commentary" if track["comm"] else ""
                    print(f"{id:2} | {lang:^5} | {name[:40]:40} | {codec[:6]:^6} | {" "*6} | {default:^7} | {" "*3} | {comm:^10}")
                print(h_bar)
            elif tracktype =="subtitles":
                # print("Subtitles:")
                for track in tracks:
                    id = track["id"]
                    lang = track["lang"]
                    name = track["name"]
                    codec = track["codec"]
                    forced = "Forced" if track["forced"] else ""
                    default = "Default" if track["default"] else ""
                    sdh = "SDH" if track["sdh"] else ""
                    comm = "Commentary" if track["comm"] else ""
                    print(f"{id:2} | {lang:^5} | {name[:40]:40} | {codec[:6]:^6} | {forced:^6} | {default:^7} | {sdh:^3} | {comm:^10}")
                print(h_bar)
        print(h_bar)
        print(f'Example: ja, de en1, def en1\n  "s" skip current group, "v" show possible codes, "f" show filenames in group, "ff" show filepaths')
        print(h_bar)
        user_input = input(f"Group {category_count + 1} contains {group_filecount} " + ("files." if group_filecount > 1 else "file.") + " \nCodes please:\n")

        # Skip the current group
        if user_input == "s":
            return user_input
        # Show all possible language codes
        elif user_input == "v":
            print(h_bar)
            print("Possible values:")
            for alias, langcode in langs.items():
                print(f"{alias:4} | {langcode[0]}")
            print(h_bar)
            input("Press Enter key to continue...")
            continue
        # List the filenames of all files in the current group
        elif user_input == "f":
            print(h_bar)
            print(f"{group_filecount} " + ("files" if group_filecount > 1 else "file") + " will be affected:")
            for file_path in movies_in_cat:
                print(os.path.basename(file_path))
            print(h_bar)
            input("Press Enter to continue...")
            continue
        # List the absolute paths of all files in the current group
        elif user_input == "ff":
            print(h_bar)
            print(f"{group_filecount} " + ("files" if group_filecount > 1 else "file") + " will be affected:")
            for file_path in movies_in_cat:
                print(os.path.abspath(file_path))
            print(h_bar)
            input("Press Enter to continue...")
            continue
        # Split the user input
        inputs = []
        inputs.extend(user_input.split(",")[0].split())
        vcode_count = len(user_input.split(",")[0].split())
        try:
            inputs.extend(user_input.split(",")[1].split())
            acode_count = len(user_input.split(",")[1].split())
        except IndexError:
            pass
        try:
            inputs.extend(user_input.split(",")[2].split())
            scode_count = len(user_input.split(",")[2].split())
        except IndexError:
            pass
        inputs_stripped = [s.replace('1', '') for s in inputs]
        match_input = re.match(pattern_input, user_input)
        if video_track_count != vcode_count:
            print("Video code count does not match video track count, try again.")
            sleep(1)
        elif audio_track_count != acode_count:
            print("Audio code count does not match audio track count, try again.")
            sleep(1)
        elif subtitle_track_count != scode_count:
            print("Subtitle code count does not match subtitle track count, try again.")
            sleep(1)
        elif not match_input:
            print("Invalid code(s) or syntax, try again.")
            sleep(1)
        elif match_input and all(input in langs for input in inputs_stripped): # Check if all language codes are in the list
            return user_input
        else:
            fehler=set(inputs) - langs.keys()
            print(fehler)
            print("Invalid language code(s), try again.")
            sleep(1)

def fetch_json(file_path):
    # Get all mkv info as JSON
    mkvmerge_command = ["mkvmerge", "-J", file_path]
    try:
        mkvmerge_json = json.loads((subprocess.check_output(mkvmerge_command)))
    except subprocess.CalledProcessError:
        print(f"Error while extracting track information for {file_path}")
    return mkvmerge_json

def track_exists(track, prop, alternative=None, fallback=False):
    # Check if the desired json element exists and return an alternative or a fallback if not
    if prop in track["properties"]:
        return track["properties"][prop]
    elif alternative and alternative in track["properties"]:
        return track["properties"][alternative]
    else:
        return fallback
    
def get_track_info(mkvmerge_json):
    track_info = {}
    global sub_codec_replacements

    for track in mkvmerge_json["tracks"]:
        # Type
        track_type = track["type"]
        # Codec
        track_codec = track["codec"]
        if track_codec in sub_codec_replacements:
            track_codec = sub_codec_replacements[track_codec]
        # ID
        track_id = track["id"]
        # Language, prefer newer ietf language code over legacy code
        track_lang = track_exists(track, prop="language_ietf", alternative="language", fallback="und")
        # Name
        track_name = track_exists(track, prop="track_name", fallback="empty")
        # Forced flag
        track_forced = track_exists(track, prop="forced_track")
        # Default flag
        track_default = track_exists(track, prop="default_track")
        # SDH flag
        track_sdh = track_exists(track, prop="flag_hearing_impaired")
        # Commentary flag
        track_comm = track_exists(track, prop="flag_commentary")

        video_fields = {
            "id": track_id,
            "lang": track_lang,
            "name": track_name,
            "codec": track_codec
        }
        audio_fields = {
            "id": track_id,
            "lang": track_lang,
            "name": track_name,
            "codec": track_codec,
            "default": track_default,
            "comm": track_comm
        }
        subtitle_fields = {
            "id": track_id,
            "lang": track_lang,
            "name": track_name,
            "codec": track_codec,
            "forced": track_forced,
            "default": track_default,
            "sdh": track_sdh,
            "comm": track_comm
        }
        
        # Sort track info by track type as key and a list of track dictionaries as value, which store the details as key:value pairs
        if track_type == "video" and "video" in track_info:
            track_info["video"].append(video_fields)
        elif track_type == "video":
            track_info["video"] = [video_fields]
        elif track_type == "audio" and "audio" in track_info:
            track_info["audio"].append(audio_fields)
        elif track_type == "audio":
            track_info["audio"] = [audio_fields]
        elif track_type == "subtitles" and  "subtitles" in track_info:
            track_info["subtitles"].append(subtitle_fields)
        elif track_type == "subtitles":
            track_info["subtitles"] = [subtitle_fields]
        else:
            print("Parsing json failed.")
    return track_info

def create_cat(track_info): # Create distinctive categories based on track information
    cat = ""
    for tracktype, tracks in track_info.items():
        if tracktype == "video":
            for track in tracks:
                cat += f"{track["id"]}{track["lang"]}"
        elif tracktype =="audio":
            for track in tracks:
                cat += f"{track["id"]}{track["lang"]}{track["name"]}{track["default"]}"
        elif tracktype =="subtitles":
            for track in tracks:
                cat += f"{track["id"]}{track["lang"]}{track["name"]}{track["codec"]}{track["forced"]}{track["default"]}{track["sdh"]}{track["comm"]}"
    return tuple((cat,))

# Fetch video, audio and subtitle information for mkv files and optionally sort them into categories
def process_video_files(directory, single_folder, create_categories=True):
    category_dict = {}
    mkv_files = {}
    if not single_folder:
        with tqdm(desc="Sorting mkvs into categories", unit=" files", ncols=100) as pbar:
            mkv_count = 0
            pbar.set_postfix({"mkv files": mkv_count})
            for filename in os.listdir(directory): # scan the root/base directory for .mkv files
                pbar.update(1)
                match_unwanted = re.match(pattern_unwanted, filename) # Ignore trailers, samples
                if filename.endswith(".mkv") and not match_unwanted:
                    mkv_count += 1
                    pbar.set_postfix({"mkv files": mkv_count})
                    file_path = os.path.join(directory, filename)
                    # Get detailed mkv information as JSON
                    mkvmerge_json = fetch_json(file_path)
                    # Collect only the info needed for sorting and selecting
                    track_info = get_track_info(mkvmerge_json)
                    # Store track info for later use
                    mkv_files[file_path] = track_info
                    if create_categories:
                        # Create a unique category based on track information
                        cat = create_cat(track_info)
                        # Sort file paths into groups
                        if cat in category_dict:
                            category_dict[cat].append(file_path)
                        else:
                            category_dict[cat] = [file_path]
            for root, dirs, files in os.walk(directory): # scan subfolders recursively
                dirs[:] = [d for d in dirs if d.lower() not in ignore_dirs] # ignore folders containing extras etc.
                for dir in dirs:
                    for filename in os.listdir(os.path.join(root, dir)):
                        pbar.update(1)
                        match_unwanted = re.match(pattern_unwanted, filename)
                        if filename.endswith(".mkv") and not match_unwanted:
                            mkv_count += 1
                            pbar.set_postfix({"mkv files": mkv_count})
                            file_path = os.path.join(root, dir, filename)
                            # Get detailed mkv information as JSON
                            mkvmerge_json = fetch_json(file_path)
                            # Collect only the info needed for sorting and selecting
                            track_info = get_track_info(mkvmerge_json)
                            # Store track info for later use
                            mkv_files[file_path] = track_info
                            if create_categories:
                                # Create a unique category based on track information
                                cat = create_cat(track_info)
                                # Sort file paths into groups
                                if cat in category_dict:
                                    category_dict[cat].append(file_path)
                                else:
                                    category_dict[cat] = [file_path]
    else:
        with tqdm(desc="searching", unit=" files", ncols=100) as pbar:
            mkv_count = 0
            pbar.set_postfix({"mkv files": mkv_count})
            for filename in os.listdir(directory):
                pbar.update(1)
                match_unwanted = re.match(pattern_unwanted, filename)
                if filename.endswith(".mkv") and not match_unwanted:
                    mkv_count += 1
                    pbar.set_postfix({"mkv files": mkv_count})
                    file_path = os.path.join(directory, filename)
                    # Get detailed mkv information as JSON
                    mkvmerge_json = fetch_json(file_path)
                    # Collect only the info needed for sorting and selecting
                    track_info = get_track_info(mkvmerge_json)
                    # Store track info for later use
                    mkv_files[file_path] = track_info
                    if create_categories:
                        # Create a unique category based on track information
                        cat = create_cat(track_info)
                        # Sort file paths into groups
                        if cat in category_dict:
                            category_dict[cat].append(file_path)
                        else:
                            category_dict[cat] = [file_path]
    if create_categories and category_dict == {}:
        print(f"Found no .mkv files in {directory}, exiting.")
        sys.exit(1)
    elif not create_categories:
        return mkv_files
    else:        
        return category_dict, mkv_files

def append_sub_format(track_info):
    subnames = []
    subformats = []
    for track in track_info["subtitles"]:
        subnames.append(track["name"])
        subformats.append(track["codec"])
    return subformats, subnames

def strip_counter(directory, single_folder):
    global mkvs_renamed
    pattern_appended_num = re.compile(r'^(.*?)(?:\s\(\d\))+\.mkv$') # match remuxed files that had (1), (2) etc. appended
    skipped_mkvs = []
    if not single_folder:
        with tqdm(desc="Stripping appended counters", unit=" files", ncols=100) as pbar:
            stripped_count = 0
            skipped_count = 0
            pbar.set_postfix({"renamed": stripped_count, "skipped": skipped_count})
            for filename in os.listdir(directory): # scan the root/base directory for .mkv files
                    pbar.update(1)
                    match_appended_num = re.match(pattern_appended_num, filename) # gets the filename without (1), (2) etc.
                    if match_appended_num:
                        trimmed_name = os.path.join(directory, match_appended_num.group(1)+".mkv")
                        if os.path.isfile(trimmed_name): # check if the file without the number exists
                            skipped_mkvs.append(trimmed_name)
                            skipped_count += 1
                            pbar.set_postfix({"renamed": stripped_count, "skipped": skipped_count})
                        else:
                            os.rename(os.path.join(directory, filename), trimmed_name)
                            mkvs_renamed += 1
                            stripped_count += 1
                            pbar.set_postfix({"renamed": stripped_count, "skipped": skipped_count})
            for root, dirs, files in os.walk(directory):
                dirs[:] = [d for d in dirs if d.lower() not in ignore_dirs] # ignore folders containing extras etc.
                for dir in dirs:
                    for filename in os.listdir(os.path.join(root, dir)):
                        pbar.update(1)
                        match_appended_num = re.match(pattern_appended_num, filename) # gets the filename without (1), (2) etc.
                        if match_appended_num:
                            trimmed_name = os.path.join(root, dir, match_appended_num.group(1)+".mkv")
                            if os.path.isfile(trimmed_name): # check if the file without the number exists
                                skipped_mkvs.append(trimmed_name)
                                skipped_count += 1
                                pbar.set_postfix({"renamed": stripped_count, "skipped": skipped_count})
                            else:
                                os.rename(os.path.join(root, dir, filename), trimmed_name)
                                mkvs_renamed += 1
                                stripped_count += 1
                                pbar.set_postfix({"renamed": stripped_count, "skipped": skipped_count})
    else:
        with tqdm(desc="Stripping appended counters", unit=" files", ncols=100) as pbar:
            stripped_count = 0
            skipped_count = 0
            pbar.set_postfix({"renamed": stripped_count, "skipped": skipped_count})
            for filename in os.listdir(directory):
                pbar.update(1)
                match_appended_num = re.match(pattern_appended_num, filename) # gets the filename without (1), (2) etc.
                if match_appended_num:
                    trimmed_name = os.path.join(directory, match_appended_num.group(1)+".mkv")
                    if os.path.isfile(trimmed_name): # check if the file without the number exists
                        skipped_mkvs.append(trimmed_name)
                        skipped_count += 1
                        pbar.set_postfix({"renamed": stripped_count, "skipped": skipped_count})
                    else:
                        os.rename(os.path.join(directory, filename), trimmed_name)
                        mkvs_renamed += 1
                        stripped_count += 1
                        pbar.set_postfix({"renamed": stripped_count, "skipped": skipped_count})
    if skipped_mkvs:
        print("Skipped renaming of:")
        for path in skipped_mkvs:
            print(path)            

def rename_to_nfo(directory, single_folder):
    global mkvs_renamed
    if not single_folder:
        with tqdm(desc="Renaming .mkv to match .nfo", unit=" files", ncols=100) as pbar:
            mkv_to_nfo_count = 0
            pbar.set_postfix({"renamed": mkv_to_nfo_count})
            mkv_count = 0
            nfo_count = 0
            mkvs = []
            nfos = []
            for filename in os.listdir(directory):
                pbar.update(1)
                match = re.match(pattern_unwanted, filename)
                if filename.endswith(".mkv") and not match:
                    mkv_count += 1
                    mkvs.append(filename)
                    if mkv_count > 1:
                        break
                if filename.endswith(".nfo") and not filename in ignore_nfos:
                    nfo_count +=1
                    nfos.append(filename[:-4])
                    if nfo_count > 1:
                        break
            if mkv_count == 1 and nfo_count == 1 and mkvs[0] != nfos[0] + ".mkv":
                os.rename(mkvs[0], nfos[0] + ".mkv")
                mkv_to_nfo_count += 1
                pbar.set_postfix({"renamed": mkv_to_nfo_count})
                mkvs_renamed += 1
            for root, dirs, files in os.walk(directory):
                dirs[:] = [d for d in dirs if d.lower() not in ignore_dirs] # ignore folders containing extras etc.
                for dir in dirs:
                    mkv_count = 0
                    nfo_count = 0
                    mkvs = []
                    nfos = []
                    for filename in os.listdir(os.path.join(root, dir)):
                        pbar.update(1)
                        match_unwanted = re.match(pattern_unwanted, filename) # match unwanted files
                        if filename.endswith(".mkv") and not match_unwanted:
                            mkv_count += 1
                            mkvs.append(os.path.join(root, dir, filename))
                            if mkv_count > 1:
                                break
                        if filename.endswith(".nfo") and not filename in ignore_nfos:
                            nfo_count +=1
                            nfos.append(os.path.join(root, dir, filename)[:-4])
                            if nfo_count > 1:
                                break
                    if mkv_count == 1 and nfo_count == 1 and mkvs[0] != nfos[0] + ".mkv":
                        os.rename(mkvs[0], nfos[0] + ".mkv")
                        mkv_to_nfo_count += 1
                        pbar.set_postfix({"renamed": mkv_to_nfo_count})
                        mkvs_renamed += 1
    else:
        with tqdm(desc="Renaming .mkv files to match .nfo files", unit=" mkvs", ncols=100) as pbar:
            mkv_to_nfo_count = 0
            pbar.set_postfix({"renamed": mkv_to_nfo_count})
            mkv_count = 0
            nfo_count = 0
            mkvs = []
            nfos = []
            for filename in os.listdir(directory):
                pbar.update(1)
                match = re.match(pattern_unwanted, filename)
                if filename.endswith(".mkv") and not match:
                    mkv_count += 1
                    mkvs.append(filename)
                    if mkv_count > 1:
                        break
                if filename.endswith(".nfo") and not filename in ignore_nfos:
                    nfo_count +=1
                    nfos.append(filename[:-4])
                    if nfo_count > 1:
                        break
            if mkv_count == 1 and nfo_count == 1 and mkvs[0] != nfos[0] + ".mkv":
                os.rename(mkvs[0], nfos[0] + ".mkv")
                mkv_to_nfo_count += 1
                pbar.set_postfix({"renamed": mkv_to_nfo_count})
                mkvs_renamed += 1

def extract_title(file_path):
    # Try to extract the movie name or tv show episode title from a matching .nfo and use regex on the file title as fallback
    filename = os.path.basename(file_path)
    nfo_file = os.path.splitext(file_path)[0]+".nfo"
    if os.path.isfile(nfo_file): # Check for matching .nfo file to extract the title
        try:
            with open(nfo_file, encoding="utf-8") as f:
                xml = f.read()
            root = ET.fromstring(re.sub(r"(<\?xml[^>]+\?>)", r"\1\n<root>", xml) + "</root>") # Add fake root to parse multi-episode nfos with multiple roots
            titles = []
            pattern_mul_ep_part = re.compile(r'^(.+) (\(\d\)|\d)$') # Detects numbered episodes which end with a number, "1" or "(1)" for example
            for child in root:
                titles.append(child.findtext('title'))
            if titles:
                if len(titles) == 1:
                    title = titles[0]
                elif len(titles) == 2:
                    base = []
                    part_num = []
                    for title in titles:
                        match = re.match(pattern_mul_ep_part, title)
                        if not match or len(base) > 1:
                            title = (" & ").join(titles) # Double episodes get "episode 1 & episode 2"
                            break
                        elif match.group(1) not in base:
                            base.append(match.group(1))
                            part_num.append(match.group(2))
                        else:
                            part_num.append(match.group(2))
                    if base and len(part_num) > 1:
                        title = f'{base[0]} {" & ".join(part_num)}' # Numbered double episodes get "episode 1 & 2"
                else:
                    base = []
                    part_num = []
                    for title in titles:
                        match = re.match(pattern_mul_ep_part, title)
                        if not match or len(base) > 1:
                            title = f'{", ".join(titles[:-1])} & {titles[-1]}' # Multi episodes get "episode 1, episode 2 & episode n"
                            break
                        elif match.group(1) not in base:
                            base.append(match.group(1))
                            part_num.append(match.group(2))
                        else:
                            part_num.append(match.group(2))
                    if base and len(part_num) > 1:
                        title = f'{base[0]} {part_num[0]}-{part_num[-1]}' # Numbered multi episodes get "episode 1-n"
            else:
                title = ""
        except ET.ParseError as e: # Fall back to using the filename if the parsing fails
            print(f"Error while parsing {nfo_file}: {e}\nAttempting to extract it from the filename instead.")
            match_tvshow = re.match(pattern_tvshow, filename)
            match_movie = re.match(pattern_movie, filename)
            title=""
            if match_tvshow:
                title = match_tvshow.group(1).replace("_", ":") # Replace "_" in the file name with ":" before using it as file title
            elif match_movie:
                title = match_movie.group(1).replace("_", ":") # Replace "_" in the file name with ":" before using it as file title
            else:
                pass
    else:
        match_tvshow = re.match(pattern_tvshow, filename)
        match_movie = re.match(pattern_movie, filename)
        title=""
        if match_tvshow:
            title = match_tvshow.group(1).replace("_", ":") # Replace "_" in the file name with ":" before using it as file title
        elif match_movie:
            title = match_movie.group(1).replace("_", ":") # Replace "_" in the file name with ":" before using it as file title
        else:
            pass
    return title

def split_inputs(user_input):
    # Divide the input into video, audio and subtitle parts
    video_track = user_input.split(",")[0]
    try:
        audio_tracks = user_input.split(",")[1].split()
    except IndexError:
        audio_tracks = None
    try:
        subtitle_tracks = user_input.split(",")[2].split()
    except IndexError:
        subtitle_tracks = None
    return video_track, audio_tracks, subtitle_tracks

def process_category(category_dict, cat, user_input, mkv_files):
    with tqdm(total = len(category_dict[cat]), position=1, desc="Applying changes", unit=" files", ncols=100) as pbar1:
        mkv_count = 0
        # Split the inputs into codes for each track type
        video_track, audio_tracks, subtitle_tracks = split_inputs(user_input=user_input)
        for file_path in category_dict[cat]:
            # Try to get the title from a linked .nfo and use regex on the filename as a fallback
            title = extract_title(file_path=file_path)

            # Base command for mkvpropedit that gives the episode and file its title
            mkvpropedit_cmd = [
                "mkvpropedit",
                file_path,
                "--edit", "info", "--set", f"title={title}", # Comment this out if you don't want the file title to be set to the movie or episode name
                "--edit", "track:v1", "--set", f"name={title}", # Comment this out if you don't want the video track name to be set to the movie or episode name
                "--set" if video_track != "-" else "", f"language={video_track}" if video_track != "-" else "" # Only set video track language if it is not "-"
            ]

            # Iterators used to edit multiple audio and subtitle tracks
            audio_track_number = 1
            subtitle_track_number = 1
            def fetch_var(tracktype, trackvar):
                if tracktype == "audio":
                    tracknumber = audio_track_number-1
                elif tracktype == "subtitles":
                    tracknumber = subtitle_track_number-1
                return mkv_files[file_path][tracktype][tracknumber][trackvar]
            if audio_tracks:
                for track in audio_tracks:
                    if track == "-":
                        mkvpropedit_cmd.extend([
                            "--edit", f"track:a{audio_track_number}",
                            "--set", "flag-enabled=1", # Remove this line if you want to leave tracks disabled
                        ])
                        if auto_set_flags:
                            # Existing track name and flags
                            audio_track_name = fetch_var("audio", "name")
                            audio_track_commentary = fetch_var("audio", "comm")

                            # Set the flag if the regex matches, but don't remove it if it's already set
                            flag_commentary = "1" if re.search(pattern_commentary, audio_track_name) or audio_track_commentary else "0"

                            mkvpropedit_cmd.extend([
                                "--set", f"flag-commentary={flag_commentary}",
                            ])
                        audio_track_number += 1
                    else:
                        lang_code = track[:-1] if track[-1].isdigit() else track  # Remove the appended "1" that sets a track as default from the language codes
                        flag_default = track[-1] if track[-1].isdigit() else "0"
                        flag_commentary = "1" if lang_code in comm_langs else "0"
                        name = langs[lang_code][0]
                        language = langs[lang_code][1]

                        mkvpropedit_cmd.extend([
                            "--edit", f"track:a{audio_track_number}",
                            "--set", f"flag-default={flag_default}",
                            "--set", "flag-forced=0", # Comment this out if you want to use forced flags for audio tracks
                            "--set", f"flag-commentary={flag_commentary}",
                            "--set", "flag-enabled=1", # Comment this out if you want to leave tracks disabled
                            "--set", f"name={name}",
                            "--set", f"language={language}"
                        ])
                        audio_track_number += 1
                        
            if subtitle_tracks:
                if add_sub_format:
                    # fetches a list of subtitle formats and a list of subtitle track names for the given mkv file
                    sub_formats, sub_names = append_sub_format(mkv_files[file_path])
                for track in subtitle_tracks:
                    if track == "-":
                        mkvpropedit_cmd.extend([
                            "--edit", f"track:s{subtitle_track_number}",
                            "--set", "flag-enabled=1", # Remove this line if you want to leave tracks disabled
                        ])
                        if add_sub_format:
                            # If the track is to be skipped, still append the format information for consistency
                            sub_name = sub_names[(subtitle_track_number - 1)]
                            sub_format = sub_formats[(subtitle_track_number - 1)]
                            match_sub = re.match(pattern_sub, sub_name)
                            if match_sub:
                                sub_name_base = match_sub.group(1)
                            else:
                                sub_name_base = sub_name
                            mkvpropedit_cmd.extend([
                                "--set", f"name={sub_name_base} ({sub_format})",
                            ])
                        if auto_set_flags:
                            # Existing track name and flags
                            subtitle_track_name = fetch_var("subtitles", "name")
                            subtitle_track_forced = fetch_var("subtitles", "forced")
                            subtitle_track_sdh = fetch_var("subtitles", "sdh")
                            subtitle_track_commentary = fetch_var("subtitles", "comm")

                            # Set the flag if the regex matches, but don't remove it if it's already set
                            flag_forced = "1" if re.search(pattern_forced, subtitle_track_name) or subtitle_track_forced else "0"
                            flag_sdh = "1" if re.search(pattern_sdh, subtitle_track_name) or subtitle_track_sdh else "0"
                            flag_commentary = "1" if re.search(pattern_commentary, subtitle_track_name) or subtitle_track_commentary else "0"

                            mkvpropedit_cmd.extend([
                                "--set", f"flag-forced={flag_forced}",
                                "--set", f"flag-hearing-impaired={flag_sdh}",
                                "--set", f"flag-commentary={flag_commentary}",
                            ])
                        subtitle_track_number += 1
                    else:
                        lang_code = track[:-1] if track[-1].isdigit() else track  # Remove the appended "1" from the language codes
                        flag_default = track[-1] if track[-1].isdigit() else "0"
                        flag_forced = "1" if lang_code in forced_langs else "0"
                        flag_sdh = "1" if lang_code in sdh_langs else "0"
                        flag_commentary = "1" if lang_code in comm_langs else "0"
                        name = langs[lang_code][0]
                        language = langs[lang_code][1]
                        if add_sub_format:
                            sub_format = sub_formats[(subtitle_track_number - 1)]

                        mkvpropedit_cmd.extend([
                            "--edit", f"track:s{subtitle_track_number}",
                            "--set", f"flag-default={flag_default}",
                            "--set", f"flag-forced={flag_forced}",
                            "--set", f"flag-hearing-impaired={flag_sdh}",
                            "--set", f"flag-commentary={flag_commentary}",
                            "--set", "flag-enabled=1",
                            "--set", f"name={name} ({sub_format})" if add_sub_format else f"name={name}",
                            "--set", f"language={language}",
                        ])
                        subtitle_track_number += 1
            try:
                subprocess.run(mkvpropedit_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT) # Execute mkvpropedit to work the magic
                pbar1.update(1)
                mkv_count += 1
                global mkvs_edited
                mkvs_edited += 1
                pbar1.set_postfix({"mkv files": mkv_count})
            except subprocess.CalledProcessError as e:
                print(f"Error while using mkvpropedit on {file_path}: {e}")

def main(args):
    args = parse_arguments()
    directory = args.directory
    single_folder = args.single_folder
    global mkvs_edited

    # --no_subformat supersedes the config setting
    global add_sub_format
    add_sub_format = False if args.no_subformat or not add_sub_format_cfg else True

    # --no_renaming supersedes the config setting
    rename_mkvs = False if args.no_renaming or not rename_mkvs_cfg else True

    # --no_auto_flags supersedes the config setting
    global auto_set_flags
    auto_set_flags = False if args.no_auto_flags or not auto_set_flags_cfg else True
    
    # Check if the required external programs are available on PATH and abort if not
    mkv_tools_on_path()

    if rename_mkvs:
        strip_counter(directory, single_folder)
        rename_to_nfo(directory, single_folder)

    category_dict, mkv_files = process_video_files(directory=directory, single_folder=single_folder, create_categories=True)
    categories = list(category_dict.keys()) # Create a list of categories

    with tqdm(total = len(categories), position=0, desc="Categories", unit="cat", ncols=100) as pbar:
        category_count = 0
        for cat in categories:
            movies_in_cat = []
            for movie in category_dict[cat]:
                movies_in_cat.append(movie)
            user_input = getInput(mkv_files=mkv_files, movies_in_cat=movies_in_cat, category_count=category_count) # Query user for language codes specific to the category
            if user_input == "s":
                print("Skipping current category.")
                pbar.update(1)
                category_count += 1
                continue
            process_category(category_dict=category_dict, cat=cat, user_input=user_input, mkv_files=mkv_files)
            pbar.update(1)
            category_count += 1
    exit_time = 1
    print(f"Renamed {mkvs_renamed} and edited {mkvs_edited} mkv files. Exiting in {exit_time} " + ("second." if exit_time == 1 else "seconds."))
    sleep(exit_time)
    sys.exit(0)

if __name__ == "__main__":
    args = parse_arguments()
    try:
        main(args)
    except KeyboardInterrupt:
        print("Interrupted, exiting.")
        try:
            sys.exit(130)
        except SystemExit:
            os._exit(130)