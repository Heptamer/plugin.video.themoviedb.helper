from resources.lib.addon.tmdate import get_datetime_now
from resources.lib.addon.consts import PLAYERS_URLENCODE
from resources.lib.addon.parser import try_int, del_empty_keys
from resources.lib.items.listitem import ListItem
from resources.lib.items.builder import ItemBuilder
from resources.lib.api.tmdb.api import TMDb
from resources.lib.api.trakt.api import TraktAPI
from json import dumps
from collections import defaultdict
from urllib.parse import quote_plus, quote


def get_external_ids(li, season=None, episode=None):
    trakt_api = TraktAPI()
    unique_id, trakt_type = None, None
    if li.infolabels.get('mediatype') == 'movie':
        unique_id = li.unique_ids.get('tmdb')
        trakt_type = 'movie'
    elif li.infolabels.get('mediatype') == 'tvshow':
        unique_id = li.unique_ids.get('tmdb')
        trakt_type = 'show'
    elif li.infolabels.get('mediatype') in ['season', 'episode']:
        unique_id = li.unique_ids.get('tvshow.tmdb')
        trakt_type = 'show'
    if not unique_id or not trakt_type:
        return
    trakt_id = trakt_api.get_id(id_type='tmdb', unique_id=unique_id, trakt_type=trakt_type, output_type='trakt')
    if not trakt_id:
        return
    details = trakt_api.get_details(trakt_type, trakt_id, extended=None)
    if not details:
        return
    if li.infolabels.get('mediatype') in ['movie', 'tvshow', 'season']:
        return {
            'unique_ids': {
                'tmdb': unique_id,
                'tvdb': details.get('ids', {}).get('tvdb'),
                'imdb': details.get('ids', {}).get('imdb'),
                'slug': details.get('ids', {}).get('slug'),
                'trakt': details.get('ids', {}).get('trakt')}}
    episode_details = trakt_api.get_details(
        trakt_type, trakt_id,
        season=season or li.infolabels.get('season'),
        episode=episode or li.infolabels.get('episode'),
        extended=None)
    if episode_details:
        return {
            'unique_ids': {
                'tvshow.tmdb': unique_id,
                'tvshow.tvdb': details.get('ids', {}).get('tvdb'),
                'tvshow.imdb': details.get('ids', {}).get('imdb'),
                'tvshow.slug': details.get('ids', {}).get('slug'),
                'tvshow.trakt': details.get('ids', {}).get('trakt'),
                'tvdb': episode_details.get('ids', {}).get('tvdb'),
                'tmdb': episode_details.get('ids', {}).get('tmdb'),
                'imdb': episode_details.get('ids', {}).get('imdb'),
                'slug': episode_details.get('ids', {}).get('slug'),
                'trakt': episode_details.get('ids', {}).get('trakt')}}


def get_item_details(tmdb_type, tmdb_id, season=None, episode=None, language=None):
    tmdb_api = TMDb(language=language) if language else TMDb()
    ib = ItemBuilder(tmdb_api=tmdb_api)
    details = ib.get_item(tmdb_type, tmdb_id, season, episode)
    try:
        artwork = details['artwork']
        details = details['listitem']
    except (KeyError, TypeError):
        return
    if not details:
        return
    details['art'] = ib.get_item_artwork(artwork, is_season=True if season else False)
    details = ListItem(**details)
    details.infolabels['mediatype'] == 'movie' if tmdb_type == 'movie' else 'episode'
    details.set_details(details=get_external_ids(details, season=season, episode=episode))
    return details


def _get_language_details(tmdb_type, tmdb_id, season=None, episode=None, language=None):
    details = TMDb().get_request_lc(tmdb_type, tmdb_id, 'translations')
    if not details or not details.get('translations'):
        return

    item = {}
    for i in details['translations']:
        if i.get('iso_639_1') == language:
            item['title'] = i.get('data', {}).get('title') or i.get('data', {}).get('name')
            item['plot'] = i.get('data', {}).get('overview')
            return item


def _get_language_item(tmdb_type, tmdb_id, season=None, episode=None, language=None, year=None):
    item = _get_language_details(tmdb_type, tmdb_id, language=language)
    if not item:
        return

    item['showname'] = item['clearname'] = item['tvshowtitle'] = item.get('title')
    item['name'] = f'{item["title"]} ({year})' if item.get('title') and year else None
    if season is None or episode is None:
        return item

    episode = _get_language_details(tmdb_type, tmdb_id, season, episode, language=language)
    if not episode:
        return item

    item['title'] = episode.get('title')
    item['plot'] = episode.get('plot') or item.get('plot')
    item['name'] = f'{item["showname"]} S{try_int(season):02d}E{try_int(episode):02d}' if item.get('showname') else None
    return item


def get_language_details(base, tmdb_type, tmdb_id, season=None, episode=None, language=None, year=None):
    if not language:
        return base
    item = _get_language_item(tmdb_type, tmdb_id, season, episode, language, year)
    if not item:
        return base
    item = {k: v or base.get(k) for k, v in item.items()}  # Fallback to default key in base if translation is empty
    item = _url_encode_item(item)
    for k, v in item.items():
        base[f'{language}_{k}'] = v
    return _url_encode_item(base)


def _url_encode_item(item, base=None):
    base = base or item.copy()
    for k, v in base.items():
        if k not in PLAYERS_URLENCODE:
            continue
        v = f'{v}'
        d = {k: v, f'{k}_meta': dumps(v)}
        for key, value in d.items():
            item[key] = value.replace(',', '')
            item[key + '_+'] = value.replace(',', '').replace(' ', '+')
            item[key + '_-'] = value.replace(',', '').replace(' ', '-')
            item[key + '_escaped'] = quote(quote(value))
            item[key + '_escaped+'] = quote(quote_plus(value))
            item[key + '_url'] = quote(value)
            item[key + '_url+'] = quote_plus(value)
    return item


def get_detailed_item(tmdb_type, tmdb_id, season=None, episode=None, details=None):
    details = details or get_item_details(tmdb_type, tmdb_id, season, episode)
    if not details:
        return None
    item = defaultdict(lambda: '_')
    item['id'] = item['tmdb'] = tmdb_id
    item['imdb'] = details.unique_ids.get('imdb')
    item['tvdb'] = details.unique_ids.get('tvdb')
    item['trakt'] = details.unique_ids.get('trakt')
    item['slug'] = details.unique_ids.get('slug')
    item['season'] = season
    item['episode'] = episode
    item['originaltitle'] = details.infolabels.get('originaltitle')
    item['title'] = details.infolabels.get('tvshowtitle') or details.infolabels.get('title')
    item['showname'] = item['clearname'] = item['tvshowtitle'] = item.get('title')
    item['year'] = details.infolabels.get('year')
    item['name'] = f'{item.get("title")} ({item.get("year")})'
    item['premiered'] = item['firstaired'] = item['released'] = details.infolabels.get('premiered')
    item['plot'] = details.infolabels.get('plot')
    item['cast'] = item['actors'] = " / ".join([i.get('name') for i in details.cast if i.get('name')])
    item['thumbnail'] = details.art.get('thumb')
    item['poster'] = details.art.get('poster')
    item['fanart'] = details.art.get('fanart')
    item['now'] = get_datetime_now().strftime('%Y%m%d%H%M%S%f')

    if tmdb_type == 'tv' and season is not None and episode is not None:
        item['id'] = item['epid'] = item['eptvdb'] = item.get('tvdb')
        item['title'] = details.infolabels.get('title')  # Set Episode Title
        item['name'] = f'{item.get("showname")} S{try_int(season):02d}E{try_int(episode):02d}'
        item['season'] = season
        item['episode'] = episode
        item['showpremiered'] = details.infoproperties.get('tvshow.premiered')
        item['showyear'] = details.infoproperties.get('tvshow.year')
        item['eptmdb'] = details.unique_ids.get('tmdb')
        item['epimdb'] = details.unique_ids.get('imdb')
        item['eptrakt'] = details.unique_ids.get('trakt')
        item['epslug'] = details.unique_ids.get('slug')
        item['tmdb'] = details.unique_ids.get('tvshow.tmdb')
        item['imdb'] = details.unique_ids.get('tvshow.imdb')
        item['tvdb'] = details.unique_ids.get('tvshow.tvdb')
        item['trakt'] = details.unique_ids.get('tvshow.trakt')
        item['slug'] = details.unique_ids.get('tvshow.slug')

    return _url_encode_item(item)


def get_playerstring(tmdb_type, tmdb_id, season=None, episode=None, details=None):
    if not details:
        return None
    playerstring = {}
    playerstring['tmdb_type'] = 'episode' if tmdb_type in ['episode', 'tv'] else 'movie'
    playerstring['tmdb_id'] = tmdb_id
    playerstring['imdb_id'] = details.unique_ids.get('imdb')
    if tmdb_type in ['episode', 'tv']:
        playerstring['imdb_id'] = details.unique_ids.get('tvshow.imdb')
        playerstring['tvdb_id'] = details.unique_ids.get('tvshow.tvdb')
        playerstring['season'] = season
        playerstring['episode'] = episode
    return dumps(del_empty_keys(playerstring))
