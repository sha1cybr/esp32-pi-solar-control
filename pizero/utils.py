import asyncio

from network import STA_IF, WLAN


async def connect_to_wifi(ssid='SSID', password='PASSWORD'):
    wlan = WLAN(STA_IF)
    wlan.active(True)
    
    if not wlan.isconnected():
        print('Connecting to WiFi...')
        wlan.connect(ssid, password)
        while not wlan.isconnected():
            print("Not connected yet.. sleeping")
            await asyncio.sleep(1)
    print('Network config:', wlan.ifconfig())
    return wlan.ifconfig()[0]  # Return IP address

def parse_query_string(query_string):
    """ return params from query string """
    if len(query_string) == 0:
        return {}
    query_params_string = query_string.split("&")
    query_params = {}
    for param_string in query_params_string:
        param = param_string.split("=")
        key = param[0]
        if len(param) == 1:
            value = ""
        else:
            value = param[1]
        query_params[key] = unquote(value)
    return query_params


def unquote(string):
    """ unquote string """
    if not string:
        return ""

    if isinstance(string, str):
        string = string.encode("utf-8")

    bits = string.split(b"%")
    if len(bits) == 1:
        return string.decode("utf-8")

    res = bytearray(bits[0])
    append = res.append
    extend = res.extend

    for item in bits[1:]:
        try:
            append(int(item[:2], 16))
            extend(item[2:])
        except KeyError:
            append(b"%")
            extend(item)

    return bytes(res).decode("utf-8")
