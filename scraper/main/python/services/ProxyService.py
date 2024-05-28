import zipfile
from pathlib import Path

from db import DatabaseConnector


def get_proxies():
    """
    Get all proxies from the database, plus a None value for running without a proxy.
    """
    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT username, pass, host, port FROM proxies;")
        proxies = cursor.fetchall()

    formatted_proxies = []
    for proxy in proxies:
        formatted_proxies.append(Proxy(proxy[0], proxy[1], proxy[2], proxy[3]))

    formatted_proxies.append(None)

    return formatted_proxies


def find_first_proxy():
    """
    :return: The first proxy found in the database, or None if no proxies are found.
    """
    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT username, pass, host, port FROM proxies;")
        proxy = cursor.fetchone()

    if proxy is None:
        return None

    formatted_proxy = Proxy(proxy[0], proxy[1], proxy[2], proxy[3])
    return formatted_proxy


def configure_proxy(chrome_options, proxy):
    if proxy is None:
        return chrome_options

    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        },
        "minimum_chrome_version":"22.0.0"
    }
    """
    background_js = """
    var config = {
            mode: "fixed_servers",
            rules: {
            singleProxy: {
                scheme: "http",
                host: "%s",
                port: parseInt(%s)
            },
            bypassList: ["localhost"]
            }
        };
    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});
    function callbackFn(details) {
        return {
            authCredentials: {
                username: "%s",
                password: "%s"
            }
        };
    }
    chrome.webRequest.onAuthRequired.addListener(
                callbackFn,
                {urls: ["<all_urls>"]},
                ['blocking']
    );
    """ % (proxy.host, proxy.port, proxy.username, proxy.password)

    folder_path = Path(__file__).parent.joinpath('../../resources/proxy_extensions').resolve()
    path_string = str(folder_path).replace('\\', '/')

    plugin_file = f"{path_string}/{proxy.host}_{proxy.port}.zip"
    with zipfile.ZipFile(plugin_file, 'w') as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)

    chrome_options.add_extension(plugin_file)

    return chrome_options


class Proxy(object):
    def __init__(self, username, password, host, port):
        self.username = username
        self.password = password
        self.host = host
        self.port = port

    def __str__(self):
        return f"http://{self.username}:{self.password}@{self.host}:{self.port}"
