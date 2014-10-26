import logging
from ldap3 import Server, Connection, SEARCH_SCOPE_WHOLE_SUBTREE, LDAPException
from apps.auth.errors import AuthError, NotFoundAuthError
from apps.auth.service import AuthService
from superdesk import get_resource_service
from superdesk.resource import Resource
from superdesk.services import BaseService
from superdesk.utc import utcnow
from flask import current_app as app
import superdesk

logger = logging.getLogger(__name__)


class ImportUserProfileResource(Resource):
    """
    Resource class used while adding a new user from UI when AD is active.
    """

    url = "import_profile"

    schema = {
        'username': {
            'type': 'string',
            'required': True,
            'minlength': 1
        },
        'password': {
            'type': 'string',
            'required': True,
            'minlength': 5
        },
        'profile_to_import': {
            'type': 'string',
            'required': True,
            'minlength': 1
        }
    }

    datasource = {
        'source': 'users',
        'projection': {
            'password': 0,
            'preferences': 0
        }
    }

    extra_response_fields = [
        'display_name',
        'username',
        'is_active',
        'needs_activation'
    ]

    item_methods = []
    resource_methods = ['POST']


class ADAuth:
    """
    Handles Authentication against Active Directory.
    """

    def __init__(self, host, port, base_filter, user_filter, profile_attributes, fqdn):
        """
        Initializes the AD Server
        :param host: ldap server. for example ldap://aap.com.au
        :param port: default port is 389
        :param base_filter:
        :param user_filter:
        :param profile_attributes:
        """
        self.ldap_server = Server(host, (port if port is not None else 389))

        self.fqdn = fqdn
        self.base_filter = base_filter
        self.user_filter = user_filter
        self.profile_attrs = profile_attributes

    def authenticate_and_fetch_profile(self, username, password, username_for_profile=None):
        """
        Authenticates a user with credentials username and password against AD. If authentication is successful then it
        fetches a profile of a user identified by username_for_profile and if found the profile is returned.
        :param username: LDAP username
        :param password: LDAP password
        :param username_for_profile: Username of the profile to be fetched
        :return: user profile base on the LDAP_USER_ATTRIBUTES
        """

        if username_for_profile is None:
            username_for_profile = username

        if self.fqdn is not None:
            username = username + "@" + self.fqdn

        try:
            ldap_conn = Connection(self.ldap_server, auto_bind=True, user=username, password=password)

            user_filter = self.user_filter.format(username_for_profile)
            logger.info('base filter:{} user filter:{}'.format(self.base_filter, user_filter))

            with ldap_conn:
                result = ldap_conn.search(self.base_filter, user_filter, SEARCH_SCOPE_WHOLE_SUBTREE,
                                          attributes=list(self.profile_attrs.keys()))

                response = dict()

                if result:
                    user_profile = ldap_conn.response[0]['attributes']

                    for ad_profile_attr, sd_profile_attr in self.profile_attrs.items():
                        response[sd_profile_attr] = \
                            user_profile[ad_profile_attr] if user_profile.__contains__(ad_profile_attr) else ''

                        response[sd_profile_attr] = response[sd_profile_attr][0] \
                            if isinstance(response[sd_profile_attr], list) else response[sd_profile_attr]

                return response
        except LDAPException as e:
            logger.error("Exception occurred. Login failed for user {}".format(username), e)
            raise AuthError()


class ADAuthService(AuthService):

    def authenticate(self, credentials):
        """
        Authenticates the user against Active Directory
        :param credentials: an object having "username" and "password" attributes
        :return: if success returns User object, otherwise throws Error
        """
        settings = app.settings
        ad_auth = ADAuth(settings['LDAP_SERVER'], settings['LDAP_SERVER_PORT'], settings['LDAP_BASE_FILTER'],
                         settings['LDAP_USER_FILTER'], settings['LDAP_USER_ATTRIBUTES'], settings['LDAP_FQDN'])

        username = credentials.get('username')
        password = credentials.get('password')
        profile_to_import = credentials['profile_to_import'] if 'profile_to_import' in credentials else username

        profile_to_be_created = True
        if credentials['profile_to_be_created'] and credentials['profile_to_be_created'] == 'false':
            profile_to_be_created = False

        user_data = ad_auth.authenticate_and_fetch_profile(username, password, username_for_profile=profile_to_import)
        if len(user_data) == 0:
            raise NotFoundAuthError()

        if profile_to_be_created:
            user = superdesk.get_resource_service('users').find_one(username=profile_to_import, req=None)

            if not user:
                user_data['username'] = profile_to_import
                user_data['is_active'] = True
                user_data[app.config['DATE_CREATED']] = user_data[app.config['LAST_UPDATED']] = utcnow()

                superdesk.get_resource_service('users').post([user_data])
            else:
                user_data[app.config['LAST_UPDATED']] = utcnow()
                superdesk.get_resource_service('users').patch(user.get('_id'), user_data)

            user = superdesk.get_resource_service('users').find_one(username=profile_to_import, req=None)
        else:
            user = user_data

        return user


class ImportUserProfileService(BaseService):
    """
    Service Class for endpoint /import_profile
    """
    def on_create(self, docs):
        doc = docs[0]
        doc['profile_to_be_created'] = 'false'
        time_stamp = doc[app.config['LAST_UPDATED']]
        profile_to_import = doc['profile_to_import']

        doc = get_resource_service('auth').authenticate(doc)

        doc[app.config['LAST_UPDATED']] = doc[app.config['DATE_CREATED']] = time_stamp
        doc['username'] = profile_to_import
        doc['is_active'] = True
        doc['user_type'] = 'user'

        docs[0] = doc
