import xml.etree.ElementTree as elemtree
from datetime import datetime
import requests, time, sys, os, re, math, json, base64, urllib
import mapbox
from routemap import convert_gps, convert_pos, Mapframe, RouteMap

class ApiKeyError(Exception):
    pass

route_type_str = {0: '공용', 1: '공항', 2: '마을', 3: '간선', 4: '지선', 5: '순환', 6: '광역', 7: '인천', 8: '경기', 9: '폐지', 10: '투어',
    11: '직행', 12: '좌석', 13: '일반', 14: '광역', 15: '따복', 16: '순환', 21: '농어촌직행', 22: '농어촌좌석', 23: '농어촌', 30: '마을', 
    41: '고속', 42: '시외좌석', 43: '시외일반', 51: '공항리무진', 52: '공항좌석', 53: '공항일반',
    61: '일반', 62: '급행', 63: '좌석', 64: '심야', 65: '마을'}

cache_dir = 'cache'

def convert_busan_bus_type(type_str):
    if type_str[:2] == '일반':
        return 61
    elif type_str[:2] == '급행':
        return 62
    elif type_str[:2] == '좌석':
        return 63
    elif type_str[:2] == '심야':
        return 64
    elif type_str[:2] == '마을':
        return 65
    else:
        return 0

def convert_type_to_region(route_type):
    if route_type <= 10:
        return '서울'
    elif route_type <= 60:
        return '경기'
    else:
        return '부산'

def get_seoul_bus_stops(key, routeid):
    # 서울 버스 정류장 목록 조회
    params = {'serviceKey': key, 'busRouteId': routeid}
    
    route_api_res = requests.get('http://ws.bus.go.kr/api/rest/busRouteInfo/getStaionByRoute', params = params).text
    route_api_tree = elemtree.fromstring(route_api_res)

    api_err = int(route_api_tree.find('./msgHeader/headerCd').text)
    
    if api_err == 7:
        raise ApiKeyError()
    
    if api_err != 0 and api_err != 4:
        raise ValueError(route_api_tree.find('./msgHeader/headerMsg').text)

    route_api_body = route_api_tree.find('./msgBody')
    bus_stop_items = route_api_body.findall('./itemList')

    bus_stops = []
    for i in bus_stop_items:
        stop = {}
        stop['arsid'] = i.find('./arsId').text
        stop['name'] = i.find('./stationNm').text
        stop['pos'] = (float(i.find('./gpsX').text), float(i.find('./gpsY').text))
        stop['is_trans'] = i.find('./transYn').text == 'Y'
        
        bus_stops.append(stop)
    
    return bus_stops

def get_gyeonggi_bus_stops(key, routeid):
    # 경기 버스 정류장 목록 조회
    params = {'serviceKey': key, 'routeId': routeid}
    
    route_api_res = requests.get('http://apis.data.go.kr/6410000/busrouteservice/getBusRouteStationList', params = params, timeout = 20).text
    route_api_tree = elemtree.fromstring(route_api_res)
    
    api_common_err = route_api_tree.find('./cmmMsgHeader/returnAuthMsg')
    if api_common_err != None:
        raise ApiKeyError(api_common_err.text)

    api_err = int(route_api_tree.find('./msgHeader/resultCode').text)

    if api_err != 0 and api_err != 4:
        raise ValueError(route_api_tree.find('./msgHeader/resultMessage').text)

    route_api_body = route_api_tree.find('./msgBody')
    bus_stop_items = route_api_body.findall('./busRouteStationList')

    bus_stops = []
    for i in bus_stop_items:
        stop = {}
        
        arsid_find = i.find('./mobileNo')
        if arsid_find:
            stop['arsid'] = arsid_find.text
        else:
            stop['arsid'] = None
        
        stop['name'] = i.find('./stationName').text
        stop['pos'] = (float(i.find('./x').text), float(i.find('./y').text))
        stop['is_trans'] = i.find('./turnYn').text == 'Y'
        
        bus_stops.append(stop)
    
    return bus_stops

def get_busan_bus_stops(key, route_id, route_bims_id):
    # 부산 버스 정류장 목록 조회
    params = {'optBusNum': route_bims_id}
    
    route_api_res = requests.get('http://bus.busan.go.kr/busanBIMS/Ajax/busLineList.asp', params = params, timeout = 20).text
    route_api_tree = elemtree.fromstring(route_api_res)

    bus_stop_items = route_api_tree.findall('./line')
    
    bus_stops = []
    for i in bus_stop_items[2:]:
        stop = {}
        
        stop['arsid'] = i.attrib['text4']
        stop['name'] = i.attrib['text1']
        stop['pos'] = (float(i.attrib['text2']), float(i.attrib['text3']))
        stop['is_trans'] = False
        
        bus_stops.append(stop)
    
    params2 = {'serviceKey': key, 'lineid': route_id}
    route_api_res2 = requests.get('https://apis.data.go.kr/6260000/BusanBIMS/busInfoByRouteId', params = params2, timeout = 20).text
    route_api_tree2 = elemtree.fromstring(route_api_res2)
    
    api_common_err = route_api_tree2.find('./cmmMsgHeader/returnAuthMsg')
    if api_common_err != None:
        raise ApiKeyError(api_common_err.text)
    
    bus_stop_items2 = route_api_tree2.findall('./body/items/item')
    for i in bus_stop_items2:
        if i.find('./rpoint').text == '1':
            bus_stops[int(i.find('./bstopidx').text) - 1]['is_trans'] = True
            break
    
    return bus_stops

def get_seoul_bus_type(key, routeid):
    # 서울 버스 노선정보 조회
    params = {'serviceKey': key, 'busRouteId': routeid}
    
    route_api_res = requests.get('http://ws.bus.go.kr/api/rest/busRouteInfo/getRouteInfo', params = params).text
    route_api_tree = elemtree.fromstring(route_api_res)

    api_err = int(route_api_tree.find('./msgHeader/headerCd').text)
    
    if api_err == 7:
        raise ApiKeyError()

    if api_err != 0 and api_err != 4:
        raise ValueError(route_api_tree.find('./msgHeader/headerMsg').text)

    route_api_body = route_api_tree.find('./msgBody/itemList')
    route_info = {}
    
    route_info['type'] = int(route_api_body.find('./routeType').text)
    route_info['name'] = route_api_body.find('./busRouteNm').text
    route_info['start'] = route_api_body.find('./stStationNm').text
    route_info['end'] = route_api_body.find('./edStationNm').text
    
    return route_info

def get_gyeonggi_bus_type(key, routeid):
    # 경기 버스 노선정보 조회
    params = {'serviceKey': key, 'routeId': routeid}
    
    route_api_res = requests.get('http://apis.data.go.kr/6410000/busrouteservice/getBusRouteInfoItem', params = params, timeout = 20).text
    route_api_tree = elemtree.fromstring(route_api_res)
    
    api_common_err = route_api_tree.find('./cmmMsgHeader/returnAuthMsg')
    if api_common_err != None:
        raise ApiKeyError(api_common_err.text)

    api_err = int(route_api_tree.find('./msgHeader/resultCode').text)

    if api_err != 0 and api_err != 4:
        raise ValueError(route_api_tree.find('./msgHeader/resultMessage').text)

    route_api_body = route_api_tree.find('./msgBody/busRouteInfoItem')
    route_info = {}
    
    route_info['type'] = int(route_api_body.find('./routeTypeCd').text)
    route_info['name'] = route_api_body.find('./routeName').text
    route_info['start'] = route_api_body.find('./startStationName').text
    route_info['end'] = route_api_body.find('./endStationName').text
    
    return route_info

def get_busan_bus_type(key, route_bims_id):
    # 부산 버스 노선정보 조회
    params = {'optBusNum': route_bims_id}
    
    route_api_res = requests.get('http://bus.busan.go.kr/busanBIMS/Ajax/busLineList.asp', params = params, timeout = 20).text
    route_api_tree = elemtree.fromstring(route_api_res)

    bus_stop_items = route_api_tree.findall('./line')
    
    bus_info_tree = bus_stop_items[0]
    route_info = {}
    
    route_info['type'] = convert_busan_bus_type(bus_info_tree.attrib['text2'])
    route_info['name'] = bus_info_tree.attrib['text1']
    route_info['start'] = bus_info_tree.attrib['text3']
    route_info['end'] = bus_info_tree.attrib['text4']
    
    return route_info

def get_seoul_bus_route(key, routeid):
    # 서울 버스 노선형상 조회
    params = {'serviceKey': key, 'busRouteId': routeid}
    
    route_api_res = requests.get('http://ws.bus.go.kr/api/rest/busRouteInfo/getRoutePath', params = params).text
    route_api_tree = elemtree.fromstring(route_api_res)

    api_err = int(route_api_tree.find('./msgHeader/headerCd').text)

    if api_err == 7:
        raise ApiKeyError()

    if api_err != 0 and api_err != 4:
        raise ValueError(route_api_tree.find('./msgHeader/headerMsg').text)

    route_api_body = route_api_tree.find('./msgBody')
    xml_route_positions = route_api_body.findall('./itemList')

    route_positions = []

    for i in xml_route_positions:
        x = float(i.find('./gpsX').text)
        y = float(i.find('./gpsY').text)
        
        route_positions.append((x, y))
    
    return route_positions

def get_gyeonggi_bus_route(key, routeid):
    # 경기 버스 노선형상 조회
    params = {'serviceKey': key, 'routeId': routeid}
    
    route_api_res = requests.get('http://apis.data.go.kr/6410000/busrouteservice/getBusRouteLineList', params = params, timeout = 20).text
    route_api_tree = elemtree.fromstring(route_api_res)
    
    api_common_err = route_api_tree.find('./cmmMsgHeader/returnAuthMsg')
    if api_common_err != None:
        raise ApiKeyError(api_common_err.text)

    api_err = int(route_api_tree.find('./msgHeader/resultCode').text)

    if api_err != 0 and api_err != 4:
        raise ValueError(route_api_tree.find('./msgHeader/resultMessage').text)

    route_api_body = route_api_tree.find('./msgBody')
    xml_route_positions = route_api_body.findall('./busRouteLineList')

    route_positions = []

    for i in xml_route_positions:
        x = float(i.find('./x').text)
        y = float(i.find('./y').text)
        
        route_positions.append((x, y))
    
    return route_positions

def get_busan_bus_route(route_name):
    # 부산 버스 노선형상 조회
    params = {'busLineId': route_name}
    encoded_params = urllib.parse.urlencode(params, encoding='cp949')
    
    route_api_res = requests.get('http://bus.busan.go.kr/busanBIMS/Ajax/busLineCoordList.asp?' + encoded_params, timeout = 20).text
    route_api_tree = elemtree.fromstring(route_api_res)
    xml_route_positions = route_api_tree.findall('./coord')
    
    if not xml_route_positions:
        return None, None
    
    route_bims_id = xml_route_positions[0].attrib['value1']
    route_positions = []

    for i in xml_route_positions[1:]:
        x = float(i.attrib['value2'])
        y = float(i.attrib['value3'])
        
        route_positions.append((x, y))
    
    return route_positions, route_bims_id

def search_seoul_bus_info(key, number):
    params = {'serviceKey': key, 'strSrch': number}
    
    list_api_res = requests.get('http://ws.bus.go.kr/api/rest/busRouteInfo/getBusRouteList', params = params).text
    list_api_tree = elemtree.fromstring(list_api_res)

    api_err = int(list_api_tree.find('./msgHeader/headerCd').text)
    
    if api_err == 7:
        raise ApiKeyError(list_api_tree.find('./msgHeader/headerMsg').text)

    if api_err != 0 and api_err != 4:
        raise ValueError(list_api_tree.find('./msgHeader/headerMsg').text)

    list_api_body = list_api_tree.find('./msgBody')
    xml_bus_list = list_api_body.findall('./itemList')

    bus_info_list = []

    for i in xml_bus_list:
        name = i.find('./busRouteNm').text
        route_id = i.find('./busRouteId').text
        start = i.find('./stStationNm').text
        end = i.find('./edStationNm').text
        route_type = int(i.find('./routeType').text)
        
        if route_type == 7 or route_type == 8:
            continue
        
        bus_info_list.append({'name': name, 'id': route_id, 'desc': start + '~' + end, 'type': route_type})
    
    return bus_info_list

def search_gyeonggi_bus_info(key, number):
    bus_info_list = []
    
    try:
        params = {'serviceKey': key, 'keyword': number}
        
        list_api_res = requests.get('http://apis.data.go.kr/6410000/busrouteservice/getBusRouteList', params = params, timeout = 20).text
        list_api_tree = elemtree.fromstring(list_api_res)
        
        api_common_err = list_api_tree.find('./cmmMsgHeader/returnAuthMsg')
        if api_common_err != None:
            raise ApiKeyError(api_common_err.text)
        
        api_err = int(list_api_tree.find('./msgHeader/resultCode').text)
        
        if api_err != 0 and api_err != 4:
            raise ValueError(list_api_tree.find('./msgHeader/resultMessage').text)
        
        if api_err != 4:
            list_api_body = list_api_tree.find('./msgBody')
            xml_bus_list = list_api_body.findall('./busRouteList')

            for i in xml_bus_list:
                name = i.find('./routeName').text
                route_id = i.find('./routeId').text
                region = i.find('./regionName').text
                route_type = int(i.find('./routeTypeCd').text)
                
                bus_info_list.append({'name': name, 'id': route_id, 'desc': region, 'type': route_type})
    except requests.exceptions.ConnectTimeout:
        print('Request Timeout')
    
    return bus_info_list

def search_busan_bus_info(key, number):
    bus_info_list = []
    params = {'serviceKey': key, 'lineno': number}
    
    list_api_res = requests.get('http://apis.data.go.kr/6260000/BusanBIMS/busInfo', params = params).text
    list_api_tree = elemtree.fromstring(list_api_res)
        
    api_common_err = list_api_tree.find('./cmmMsgHeader/returnAuthMsg')
    if api_common_err != None:
        raise ApiKeyError(api_common_err.text)
    
    api_err = int(list_api_tree.find('./header/resultCode').text)
    
    if api_err != 0:
        raise ValueError(list_api_tree.find('./header/resultMsg').text)
    
    xml_bus_list = list_api_tree.findall('./body/items/item')
    
    for i in xml_bus_list:
        name = i.find('./buslinenum').text
        route_id = i.find('./lineid').text
        start = i.find('./startpoint').text
        end = i.find('./endpoint').text
        route_type = convert_busan_bus_type(i.find('./bustype').text)
        
        bus_info_list.append({'name': name, 'id': route_id, 'desc': start + '~' + end, 'type': route_type})
    
    return bus_info_list

def search_bus_info(key, number, return_error = False):
    bus_info_list = []
    exception = None
    
    # 서울 버스 조회
    try:
        bus_info_list += search_seoul_bus_info(key, number)
    except ApiKeyError as api_err:
        exception = api_err
    except Exception as e:
        exception = ValueError('서울 버스 정보를 조회하는 중 오류가 발생했습니다: ' + str(e))
    
    # 경기 버스 조회
    try:
        bus_info_list += search_gyeonggi_bus_info(key, number)
    except ApiKeyError as api_err:
        exception = api_err
    except Exception as e:
        exception = ValueError('경기 버스 정보를 조회하는 중 오류가 발생했습니다: ' + str(e))
    
    # 부산 버스 조회
    try:
        bus_info_list += search_busan_bus_info(key, number)
    except ApiKeyError as api_err:
        exception = api_err
    except Exception as e:
        exception = ValueError('부산 버스 정보를 조회하는 중 오류가 발생했습니다: ' + str(e))
        
    rx_number = re.compile('[0-9]+')
    is_number = bool(re.match('[0-9]+$', number))
        
    def search_score(x):
        if is_number:
            match = rx_number.search(x['name'])
            if match:
                main_x = match[0]
            else:
                main_x = x['name']
            
            score = match.start(0)
            
            if x['name'] == number:
                return 0
            elif main_x == number:
                return 1
            
            if score == -1:
                return 0x7FFFFFFF
            else:
                return score * 10000 + (len(main_x) - len(number)) * 100
        else:
            if x['name'] == number:
                return ''
            else:
                return x['name']
    
    if return_error:
        return sorted(bus_info_list, key=search_score), exception
    else:
        return sorted(bus_info_list, key=search_score)

def get_naver_map(mapframe, naver_key_id, naver_key):
    route_size = mapframe.size()
    route_size_max = max(route_size)
    pos = mapframe.center()
    level = 12
    
    while 2 ** (21 - level) > route_size_max and level < 14:
        level += 1
    
    img_size = 2 ** (22 - level)
    k = img_size / 2.1
    
    if route_size[0] / img_size > 0.85 and route_size[1] / img_size > 0.85:
        map_part = [(1, -1), (-1, -1), (1, 1), (-1, 1)]
    elif route_size[0] / img_size > 0.85:
        map_part = [(1, 0), (-1, 0)]
    elif route_size[1] / img_size > 0.85:
        map_part = [(0, -1), (0, 1)]
    else:
        map_part = [(0, 0)]
        
    map_img = []
    
    for p in map_part:
        gps_pos = convert_gps((pos[0] + k * p[0], pos[1] + k * p[1]))
        map_img.append(requests.get('https://naveropenapi.apigw.ntruss.com/map-static/v2/raster?w=1024&h=1024&center={},{}&level={}&format=png&scale=2'.format(gps_pos[0], gps_pos[1], level), 
            headers={'X-NCP-APIGW-API-KEY-ID': naver_key_id, 'X-NCP-APIGW-API-KEY': naver_key}).content)
    
    result = ''
    
    for i in range(len(map_part)):
        result += '<image width="{0}" height="{0}" x="{1}" y="{2}" href="data:image/png;charset=utf-8;base64,{3}" />\n'.format(img_size, pos[0] + k * map_part[i][0] - img_size / 2, pos[1] + k * map_part[i][1] - img_size / 2, base64.b64encode(map_img[i]).decode('utf-8'))
    
    return result

def get_mapbox_map(mapframe, mapbox_key, mapbox_style):
    route_size_max = max(mapframe.size())
    level = 12
    
    while 2 ** (21 - level) > route_size_max and level < 14:
        level += 1
    
    tile_size = 2 ** (21 - level)
    
    gps_pos = convert_gps((mapframe.left, mapframe.top))
    tile_x1, tile_y1 = mapbox.deg2num(gps_pos[1], gps_pos[0], level)
    
    gps_pos = convert_gps((mapframe.right, mapframe.bottom))
    tile_x2, tile_y2 = mapbox.deg2num(gps_pos[1], gps_pos[0], level)
    
    result = '<g id="background-map">\n'
    
    tile_pos = mapbox.num2deg(tile_x1, tile_y1, level)
    pos_x1, pos_y1 = convert_pos((tile_pos[1], tile_pos[0]))
    
    style_cache_dir = cache_dir + '/' + mapbox_style.replace("/", "_")
    if not os.path.exists(style_cache_dir):
        os.makedirs(style_cache_dir)
    
    for x in range(tile_x1, tile_x2 + 1):
        for y in range(tile_y1, tile_y2 + 1):
            cache_filename = style_cache_dir + '/tile{}-{}-z{}.svg'.format(x, y, level)
            if not os.path.exists(cache_filename):
                with open(cache_filename, mode='w+', encoding='utf-8') as cache_file:
                    mapbox.load_tile(mapbox_style, mapbox_key, x, y, level, draw_full_svg = True, clip_mask = True, fp = cache_file)
            
            pos_x = pos_x1 + (x - tile_x1) * tile_size
            pos_y = pos_y1 + (y - tile_y1) * tile_size
            
            with open(cache_filename, mode='r', encoding='utf-8') as f:
                text = f.read()
                svg_match = re.search(r'<svg\s.*?>(.*)</svg>', text, re.DOTALL)
                
                if svg_match:
                    tile = svg_match[1]
                
                    result += '<g id="tile{0}-{1}-z{2}" transform="translate({3}, {4}) scale({5}, {5}) ">\n'.format(x, y, level, pos_x, pos_y, tile_size / 4096)
                    result += tile
                    result += '</g>\n'
                else:
                    raise ValueError()
            
    result += '</g>\n'
    
    return result