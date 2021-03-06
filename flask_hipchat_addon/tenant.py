import logging
import requests
import base64
from datetime import timedelta
import time

import jwt

from .addon import db, cache

_log = logging.getLogger(__name__)

ACCESS_TOKEN_CACHE = "hipchat-tokens:{oauth_id}"


class Tenant(db.Model):
    __tablename__ = 'tenant'
    id = db.Column(db.Integer, primary_key=True)
    oauth_id = db.Column(db.Text, unique=True)
    secret = db.Column(db.Text, nullable=False)
    room_id = db.Column(db.Integer, nullable=True)
    group_id = db.Column(db.Integer, nullable=True)
    group_name = db.Column(db.Text)
    homepage = db.Column(db.Text)
    token_url = db.Column(db.Text)
    capabilities_url = db.Column(db.Text)

    def __init__(self, oauth_id, secret, group_id=None, room_id=None,
                 homepage=None, capabilities_url=None,  token_url=None,
                 group_name=None, capdoc=None):
        self.oauth_id = oauth_id
        self.secret = secret
        self.room_id = room_id
        self.group_id = group_id
        self.group_name = None if not group_name else group_name
        self.homepage = homepage or None if not capdoc \
            else capdoc['links']['homepage']
        self.token_url = token_url or None if not capdoc \
            else capdoc['capabilities']['oauth2Provider']['tokenUrl']
        self.capabilities_url = capabilities_url or None if not capdoc \
            else capdoc['links']['self']

    @cache.memoize(3600)
    def get_token(self, token_only=True, scopes=None):
        if scopes is None:
            scopes = ['send_notification']

        def gen_token():
            oauth_params = {
                'grant_type': 'client_credentials',
                'scope': ' '.join(scopes)
            }

            oauth_headers = {
                'content-type': 'application/x-www-form-urlencoded',
                'Authorization': 'Basic ' + base64.b64encode(str(self.oauth_id) + ':' + str(self.secret))
            }
            resp = requests.post(self.token_url, params=oauth_params, headers=oauth_headers, timeout=10)
            if resp.status_code == 200:
                _log.debug('Token request response: ' + resp.text)
                return resp.json()
            elif resp.status_code == 401:
                _log.error('Client %s is invalid but we weren\'t notified.  Uninstalling' % self.oauth_id)
                raise OauthClientInvalidError(self)
            else:
                raise Exception("Invalid token: %s" % resp.text)

        if token_only:
            data = gen_token()
            token = data['access_token']
            return token
        else:
            return gen_token()

    def sign_jwt(self, user_id, data=None):
        if data is None:
            data = {}

        now = int(time.time())
        exp = now + timedelta(hours=1).total_seconds()

        jwt_data = {"iss": self.id,
                    "iat": now,
                    "exp": exp}

        if user_id:
            jwt_data['prn'] = user_id

        data.update(jwt_data)
        return jwt.encode(data, self.secret)

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, self.id)


class OauthClientInvalidError(Exception):
    def __init__(self, client, *args, **kwargs):
        super(OauthClientInvalidError, self).__init__(*args, **kwargs)
        self.client = client
