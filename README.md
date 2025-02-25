# mkvpropr
## Python script to interactively and recursively batch edit mkv properties in groups based on track combinations and properties

As a perfectionist hoarder who wants each track of each mkv file to have a consistent naming and the correct flags while also setting the file title, writing this script was inevitable.<br>
I used to manually edit track properties in MKVToolNix, which (especially for tv shows) is inefficient, prone to errors and slow.<br>
A step up from that was performing changes in MKVToolNix on one file, copying the resulting options and using these on a batch of other files with the same tracks.<br>
However, manually grouping files by identical track properties and then performing changes once per group in MKVToolNix was still tedious and annoying work.<br>
Which is why I wrote .bat files for each common type of audio/subtitle track combination with fixed options. Naturally, that also quickly became unwieldy (I had 20ish .bat files in the end).<br>
  
The conclusion to all of these problems is what this script does. It recursively searches all .mkv and .nfo files in all subfolders (except for excluded ones), groups them based on their video, audio and subtitle track combinations, track names, formats and flags and then lets the user decide once per group which changes should be performed on all files in the group. The .nfo is used to extract the movie/episode title, which is set as the file title.<br>
It has many convenience features I've added over the last 1,5 years and I've used it on thousands of movies and episodes, but more on that below.<br>
Before releasing the script I've tried to make it customizable enough that it can be used on a wide variety of collections with different naming schemes and preferences.

## Example usage on Star Trek: Voyager DVD remuxes (7 Seasons, 168 Episodes, 275GB, stored on NAS, accessed via SMB)
![Gif that shows how the 168 episodes of Star Trek: Voyager are edited with mkvpropr in less than a minute.](/assets/example_gifs/mkvp_tvshow_voyager.gif)
Explanation:
In this ~1min gif I've interactively set the
1. file title and video track name based on the episode name in matching .nfo files (or extracted from the filename for multi-episode files)
2. video track language to "en"
3. 1st audio track language to "de"
4. 1st audio track name to "Deutsch"
5. 2nd audio track language to "en"
6. 2nd audio track name to "English"
7. 2nd audio track default flag to "1"
8. 1st subtitle track language to "de"
9. 1st subtitle track name to "Deutsch (VOB)"
10. 2nd subtitle track language to "en"
11. 2nd subtitle track name to "English (VOB)"
12. 2nd subtitle track default flag to "1"
13. 3rd subtitle track language to "en"
14. 3rd subtitle track name to "English SDH (VOB)"
15. 3rd subtitle hearing impaired flag to "1"

for 168 files.

## How to install mkvpropr

### Prerequisites

**Required:**
1. [python](https://www.python.org/downloads/) must be installed (tested with python 3.12.3)
2. [tqdm](https://github.com/tqdm/tqdm) must be installed, I used `pip3 install tqdm`
3. [MKVToolNix](https://mkvtoolnix.download/) must be installed and on PATH

If mkvmerge or mkvpropedit are not on PATH, the script will complain and (if on Windows) open the environment variables settings with instructions on how to add them to PATH.

### Downloading the script

You can download/clone the entire repository and extract "mkvp.py" and "mkvp_config.yaml".
If you want to be able to call it from anywhere on your system (which is more convenient than supplying a path via `-d`), you can add the folder containing "mkvp.py" to your PATH.

## Usage

### Output from -h:

```
usage: mkvp.py [-h] [-d [DIRECTORY]] [-s] [--no_subformat] [--no_renaming] [--no_auto_flags]

Scan for .mkv and .nfo files in subdirectories and set file title, track names, languages and
flags.

options:
  -h, --help            show this help message and exit
  -d [DIRECTORY], --directory [DIRECTORY]
                        The directory that will be recursively scanned for .mkv and .nfo files.
  -s, --single_folder   Only scan the current folder for .mkv and .nfo files, no subdirectories.
  --no_subformat        Don't append Sub formats " (SRT)" etc. to the subtitle track names.
  --no_renaming         Don't rename .mkv files to match .nfo files and don't trim " (1)" etc. from
                        .mkv names
  --no_auto_flags       When using "-" to skip a track, don't add forced/hearing
                        impaired/commentary flags based on the track name
```

## Configuring mkvpropr
### Before running the script for the first time, you have to customize it by editing "mkvp_config.yaml" to make it fit your collection
#### langs
This holds all possible inputs that are used to edit track properties and you can and should add your own.

`langs` is a dictionary of inputs, following this format:<br>
`"what you input": ["Name of the track", "language code"]`<br>
  
Let's break it down:<br>
`"what you input"`<br>
The input can be up to 5 characters and can only contain a-z, A-Z and digits. `s`, `v`, `f` and `ff` are special inputs, so they cannot be used as regular inputs.<br>
Don't use a number as the final character!
  
`"Name of the track"`<br>
You can set the track name to an arbitrary string of your choice.<br>
For example: "English" or "English encoded by a savage lemur"
  
`"language code"`<br>
This must be a valid language code. See the appropriate [Wikipedia article](https://en.wikipedia.org/wiki/List_of_ISO_639_language_codes).

The example config provides these to get you started:
```
langs:
  "-": ["Keep Values", "Keep Values"] # Never delete this as it has a special function!
  "zxx": ["No Language", "zxx"]
  "enf": ["Forced English", "en"]
  "en": ["English", "en"]
  "ensd": ["English SDH", "en"]
  "enc": ["Commentary English", "en"]
```
If you wanted to have German as an option, you could add:<br>
`  "de": ["German", "de"]`<br>
Using "de" as the input for a track would then set its track name to "German" and its language to "de". You could also use another input like:<br>
`  "germ": ["German", "de"]`<br>
Both of these will yield the same result, but you'd use `germ` instead of `de` as input.

#### forced_langs, sdh_langs, comm_langs
If you want a specific input to also enable a flag for that track, you have to add that input to one of these lists:
```
# Language codes that get a "forced" flag (must exist in "langs")
forced_langs:
  - enf

# Language codes that get a "hearing impaired" flag (must exist in "langs")
sdh_langs:
  - ensd

# Language codes that get a "commentary" flag (must exist in "langs")
comm_langs:
  - enc
```

If you for example wanted to add a german commentary option, you'd first add something like:<br>
`  "dec": ["Commentary German", "de"]`<br>
to the `langs` dictionary and then also add<br>
`  -dec`<br>
to the `comm_langs` list.

Using "dec" as an input would then also enable the commentary flag for that track.<br>
  
Adding forced and hearing impaired flags works the same way:<br>
You have to add the input you used in `langs` to the `forced_langs` or `sdh_langs` list.

#### default flag
While forced, hearing impaired and commentary flags are hardcoded per input, the default flag is optional.<br>
Append a `1` to an input if you want the track to get the default flag (multiple default flags are possible).<br>
`en1` for example would result in the english track having the default flag enabled.

#### ignore_dirs
The script won't recurse into folders that match entries of this list. I've added standard extras folders.<br>
You can still run the script in a folder on this list if you call it in the folder itself or pass the folder name via `-d`.

#### ignore_nfos
Nfos not related to an mkv file go here. That way they can be ignored when the script checks if there's 1 mkv and 1 nfo in the folder for automatic renaming.

#### auto_set_flags
This allows to automatically set flags based on the file name, even when you skip a track via `-` as input.<br>
For example a track with "Commentary with Director Ridley Scott" as track name should not be renamed to "Commentary English" via "enc" as input since that would mean losing information.<br>
However the commentary flag might not be set for it. With auto_set_flags enabled, this track would still get the commentary flag even if you don't change it otherwise, depending on the regexes.<br>
Note: If you skip an entire group via `s`, no changes are made.

#### add_sub_format
This enables appending the subtitle format to the track name in braces. Useful when you have multiple identical subtitles with different formats. srt, pgs + vob of plain English for example.<br>
Without it, you'd end up with 3 tracks called "English". With it, you'd get "English (SRT)", "English (PGS)" and "English (VOB)" as track titles.

#### sub_codec_replacements
Depends on add_sub_format.<br>
Here you can set what you'd like to append to the track names of subtitles. If you change this, you'll also have to edit the regexes in `pattern_sub` to match. That prevents the format from being appended multiple times like this "English (SRT) (SRT)" if you re-run the script.

#### rename_mkvs
This does two things:<br>
1. It checks if there are counters appended to the file name of .mkvs (usually from remuxing via MKVToolNix) and removes them.<br>
`The Congress (2013) (1).mkv` or `The Congress (2013) (2) (1).mkv`<br>
would be renamed to `The Congress (2013).mkv` (if the resulting file already exists, renaming is skipped and a warning is logged).<br>
2. It checks if there is 1 .mkv file and 1 .nfo file in a folder and if so renames the .mkv file to match the .nfo file.<br>
This is useful when you replace an existing .mkv file with a new version of a different name but `.nfo`, `.thumb` and `-mediainfo.xml` files rely on a matching name.

#### pattern_unwanted
With this regex you can exclude files you don't want to edit. Trailers, sample files, proof files and so on.

#### pattern_tv
This regex is used as a fallback if the episode title extraction via a matching .nfo file has failed.<br>
Adjust it according to your naming scheme. If all your episodes are named `Series name SxxExx Episode` for example, you could use:<br>
`'^.* \S\d{2,4}E\d{2,4}(?: S\d{2,4}E\d{2,4})* (.*)\.mkv$'` (assuming multi-episodes are `Series name SxxExx SxxExx Episode name`)<br>
If you want to disable the fallback, set this to `'^_$'` so it never matches.

#### pattern_movie
This regex is used as a fallback if the movie title extraction via a matching .nfo file has failed.<br>
Adjust it according to your naming scheme. If your movies are named `Title (year).mkv` for example, you could use:<br>
`'^(.*)\s\(\d{4}\)\.mkv$'`<br>
If you want to disable the fallback, set this to `'^_$'` so it never matches.

### Basic usage
Either run `mkvp.py` in the root of the directory you wish to recursively edit or provide the directory via `mkvp.py -d`<br>
After scanning, extracting information and grouping the files, the script will ask you for inputs for each group of files.<br>
You can then use the codes you've added to "langs" in the config to quickly assign track names, languages and flags.

Example movie:<br>
Video track: English<br>
Audio tracks: German, English, English commentary<br>
Subtitle tracks: forced English, English, English sdh, English commentary<br>

Assuming "langs" contains an entry for each of these inputs, you can input:<br>
`en, de en1 enc, enf en1 ensd enc`<br>

The `,` separates different track types, `1` behind a code sets the default flag<br>
video code, audio code(s), subtitle code(s)<br>

The result would be:<br>
file title = movie or episode title<br>

videotrack:<br>
name = movie or episode title<br>
language = en<br>

audiotrack 1:<br>
name = Deutsch<br>
language = de<br>
audiotrack 2:<br>
name = English<br>
language = en<br>
default flag = yes<br>
audiotrack 3:<br>
name = Commentary English<br>
language = en<br>
commentary flag = yes<br>

subtitle track 1:<br>
name = Forced English<br>
language = en<br>
forced flag = yes<br>
subtitle track 2:<br>
name = English<br>
language = en<br>
default flag = yes<br>
subtitle track 3:<br>
name = English SDH<br>
language = en<br>
hearing impaired flag = yes<br>
subtitle track 4:<br>
name = Commentary English<br>
language = en<br>
commentary flag = yes<br>

If you recreate these exact settings in MKVToolNix you'll see just how much time this script can save on one file, even disregarding that it edits batches.

### Selective usage via "-"
You don't have to set the options for each track. Either skip an entire group by using `s` as the input (explained below) or skip individual tracks by using `-` instead of a user input.

Example movie:<br>
Video track: English<br>
Audio tracks: German, English, English commentary<br>
Subtitle tracks: forced English, English sdh, English commentary<br>

`-, de en1 enc, enf en1 ensd enc`<br>
This skips setting the video track name and language<br>

`en, - - -, enf en1 ensd enc`<br>
This keeps the audio tracks as they are.<br>

`en, de en1 enc, - - - -`<br>
This keeps the subtitle tracks unchanged.<br>

You can also only skip individual tracks like this (to for example keep commentary track names that often contain unique information):<br>
`en, de en1 -, enf en1 ensd -`<br>

### Special inputs
While the script is running and prompts the user for input, a few special options/inputs are available.

**s to skip**<br>
Only use `s` as input for a group to skip it.

**v to show possible input values**<br>
Only use `v` as input to show all available language codes (useful if you're unsure if you have configured a specific language code or forgot what you called it).

**f to show filenames**<br>
Only use `f` as input to show the filenames of each file in the group (this can help you make sure that you are only editing files that you want to edit).

**ff to show absolute filepaths**<br>
Only use `ff` as input to show the absolute paths of each file in the group.