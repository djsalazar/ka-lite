"""
1. Download latest translations from CrowdIn
2. Store meta data incl: percent translated, version number, language
3. Compile po to mo
4. Zip everything up at exposed URL 
5. Update JSON file used by API to tell distributed server about language pack availability
"""

import json
import os
import re
import requests
import shutil
import zipfile
import StringIO

from optparse import make_option
from django.core import management
from django.core.management.base import BaseCommand, CommandError

import settings
from utils.general import ensure_dir
from central.management.commands.cache_subtitles import get_language_name
from update_po import move_to_project_root

LOCALE_ROOT = settings.LOCALE_PATHS[0]
LANGUAGE_PACK_AVAILABILITY_FILENAME = "language_pack_availability.json"

class Command(BaseCommand):
	option_list = BaseCommand.option_list + (
		# make_option('--test', '-t', dest='test_wrappings', action="store_true", default=False, help='Running with -t will fill in current po files msgstrs with asterisks. This will allow you to quickly identify unwrapped strings in the codebase and wrap them in translation tags! Remember to delete after your finished testing.'),
		# make_option('--update_templates', '-u', dest='update_templates', action="store_true", default=False, help='Running with -n will update exposed template files with current wrapped strings.'),
	)
	help = 'Caches latest translations from CrowdIn'

	def handle(self, **options):
		cache_translations()


def cache_translations():
	## Download from CrowdIn
	# download_latest_translations() # this fcn will be broken until we get set up on CrowdIn, hopefully by next week
	
	## Loop through them, create/update meta data
	generate_metadata()
	
	## Compile
	compile_all_po_files()
	
	## Zip
	zip_language_packs()


def download_latest_translations():
	"""Download latest translations from CrowdIn to corresponding locale directory."""
	# Note this won't download anything that we haven't manually created a folder for. 
	# CrowdIn API docs on downloading translations: http://crowdin.net/page/api/download
	# CrowdIn API docs for exporting entire project to zip archive: http://crowdin.net/page/api/export
	project_id = settings.CROWDIN_PROJECT_ID
	project_key = settings.CROWDIN_PROJECT_KEY
	for lang in os.listdir(LOCALE_ROOT):
		# Download zipfile & dump into the correct locale folder
		request_url = "http://api.crowdin.net/api/project/%s/download/%s.zip?key=%s" %(project_id, lang, project_key)
		r = requests.get(request_url)
		r.raise_for_status()
		z = zipfile.ZipFile(StringIO.StringIO(r.content))
		lang_dir = os.path.join(LOCALE_ROOT, lang, "LC_MESSAGES")
		z.extractall(lang_dir)


def generate_metadata():
	"""Loop through locale folder, create or update language specific meta and create or update master file."""
	# Open master file 
	try: 
		master_file = json.loads(open(os.path.join(LOCALE_ROOT, LANGUAGE_PACK_AVAILABILITY_FILENAME)).read())
	except:
		master_file = []

	# loop through all languages in locale, generate and write metadata, update master file
	for lang in os.listdir(LOCALE_ROOT):
		if lang.endswith(".json"):
			continue
		else:
			percent_translated = calculate_percent_translated(os.path.join(LOCALE_ROOT, lang, "LC_MESSAGES"))
			lang_metadata = {
				"code": lang,
				"name": get_language_name(lang),
				"percent_translated": percent_translated,
				"version": increment_version(lang, percent_translated, os.path.join(LOCALE_ROOT, lang))
			}
			# Write local TODO(Dylan): probably don't need to write this local version - seems like a duplication of effort
			with open(os.path.join(LOCALE_ROOT, lang, "%s_metadata.json" % lang), 'w') as output:
				json.dump(lang_metadata, output)
			
			# Update master
			master_file.append(lang_metadata)

	# Save updated master
	with open(os.path.join(settings.LANGUAGE_PACK_ROOT, LANGUAGE_PACK_AVAILABILITY_FILENAME), 'w') as output:
		json.dump(master_file, output) 


def calculate_percent_translated(po_file_path):
	"""Return total percent translated of entire language"""
	# add up totals for each file
	total_strings, total_translated = 0, 0
	for po_file in os.listdir(po_file_path):
		if po_file.endswith(".po"):
			# Read it, count up filled msgids and filled msgstrs
			po_as_string = open(os.path.join(po_file_path, po_file)).read()
			total_strings += len(re.findall(r'msgid \".+\"', po_as_string))
			total_translated += len(re.findall(r'msgstr \".+\"', po_as_string))

	# Calc percent
	percent_trans = round(float(total_translated)/float(total_strings), 3) # without floats, too inexact
	return percent_trans


def increment_version(lang_code, percent_translated, lang_locale_path):
	"""Increment language pack version if translations have been updated"""
	#TODO(Dylan): this actually isn't that good of a way of knowing if things changed.. could be tricked easily.
	try:
		old_metadata = json.loads(open(os.path.join(lang_locale_path, "%s_metadata.json" % lang_code)).read())
	except:
		version = 1
	else:
		old_version = old_metadata.get("version")
		if old_metadata.get("percent_translated") != percent_translated:
			version = old_version + 1
		else: 
			version = old_version
	return version


def compile_all_po_files():
	"""Compile all po files in locale directory"""
	# before running compilemessages, ensure in correct directory
	move_to_project_root()
	management.call_command('compilemessages')


def zip_language_packs():
	"""Zip up and expose all language packs"""
	ensure_dir(settings.LANGUAGE_PACK_ROOT)
	for lang in os.listdir(LOCALE_ROOT):
		# Create a zipfile for this language
		z = zipfile.ZipFile(os.path.join(settings.LANGUAGE_PACK_ROOT, "%s_lang_pack.zip" % lang), 'w')
		# Get every single file in the directory and zip it up
		for root, dirs, files in os.walk(os.path.join(LOCALE_ROOT, lang)):
			for f in files:
				if f.endswith(".json"):
					z.write(os.path.join(root, f), arcname=os.path.basename(f))	
				else:
					z.write(os.path.join(root, f), arcname=os.path.join("LC_MESSAGES", os.path.basename(f)))	
		z.close()





