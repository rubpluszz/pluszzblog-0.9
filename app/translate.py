import json
import requests
from flask import current_app
from flask_babel import _
import translators as ts


def translate(text, dest_language):
    try:
        r = ts.google(text, to_language=dest_language, if_use_cn_host=True)
        return r
    except Exception as e:
        return _('Error: the translation service failed.')
    
   