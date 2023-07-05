import xml.etree.ElementTree as elemtree
from datetime import datetime
import requests, time, sys, os, re, math, json, base64, argparse, urllib
import mapbox

route_type_str = {0: '공용', 1: '공항', 2: '마을', 3: '간선', 4: '지선', 5: '순환', 6: '광역', 7: '인천', 8: '경기', 9: '폐지', 10: '투어',
    11: '직행', 12: '좌석', 13: '일반', 14: '광역', 15: '따복', 16: '순환', 21: '농어촌직행', 22: '농어촌좌석', 23: '농어촌', 30: '마을', 
    41: '고속', 42: '시외좌석', 43: '시외일반', 51: '공항리무진', 52: '공항좌석', 53: '공항일반',
    61: '일반', 62: '급행', 63: '좌석', 64: '심야', 65: '마을'}
key = ''
naver_key_id = ''
naver_key = ''

cache_dir = 'cache'

origin_tile = (3490, 1584)

def convert_pos(pos):
    lat_rad = math.radians(pos[1])
    n = 1 << 12
    x = ((pos[0] + 180.0) / 360.0 * n - origin_tile[0]) * 512
    y = ((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n - origin_tile[1]) * 512
    
    return (x, y)

def convert_gps(pos):
    n = 1 << 12
    lon_deg = (pos[0] / 512 + origin_tile[0]) / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * (pos[1] / 512 + origin_tile[1]) / n)))
    lat_deg = math.degrees(lat_rad)
    
    return (lon_deg, lat_deg)

def distance(pos1, pos2):
    return math.sqrt((pos2[0] - pos1[0]) ** 2 + (pos2[1] - pos1[1]) ** 2)
    
def distance_from_segment(pos, pos1, pos2):
    d_pos12 = (pos2[0] - pos1[0]) ** 2 + (pos2[1] - pos1[1]) ** 2
    
    if d_pos12 == 0:
        return distance(pos, pos1)
    
    dot = (pos2[0] - pos1[0]) * (pos[0] - pos1[0]) + (pos[1] - pos1[1]) * (pos2[1] - pos1[1])
    param = dot / d_pos12
    
    if param < 0:
        return distance(pos, pos1)
    elif param > 1:
        return distance(pos, pos2)
    else:
        return distance(pos, (pos1[0] + param * (pos2[0] - pos1[0]), pos1[1] + param * (pos2[1] - pos1[1])))

def find_nearest_point(pos, points):
    min_dist = distance(points[0], pos)
    t_point = 0
    
    for i in range(len(points)):
        dist = distance(points[i], pos)
        
        if min_dist > dist:
            t_point = i
            min_dist = dist
    
    return t_point

def get_point_segment(points, start, end, dist):
    idx_prev = start
    idx_next = end
    
    i = end
    for i in range(end + 1, len(points)):
        if distance(points[i], points[end]) > dist:
            break
    idx_next = i
    
    i = start
    for i in range(start - 1, -1, -1):
        if distance(points[i], points[start]) > dist:
            break
    idx_prev = i
    
    return idx_prev, idx_next
    
    
def get_text_width(text):
    result = 0
    
    for i in text:
        if re.match(r'[\.\(\)]', i):
            result += 0.2
        elif re.match(r'[0-9a-z\-]', i):
            result += 0.6
        elif re.match(r'[A-Z]', i):
            result += 0.8
        else:
            result += 1
    
    return result

def check_collision(r1, r2):
    if r1[0] < r2[0] + r2[2] and r1[0] + r1[2] > r2[0] and r1[1] < r2[1] + r2[3] and r1[1] + r1[3] > r2[1]:
        if r2[0] > r1[0]:
            dx = r1[0] + r1[2] - r2[0]
        else:
            dx = r2[0] + r2[2] - r1[0]
            
        if r2[1] > r1[1]:
            dy = r1[1] + r1[3] - r2[1]
        else:
            dy = r2[1] + r2[3] - r1[1]
            
        return dx * dy
    return 0
    
def get_collision_score(new_rect, rects, points):
    collision = 0
    for r in rects:
        collision += check_collision(r, new_rect)
    
    for p in points:
        collision += check_collision((p[0] - 2, p[1] - 2, 4, 4), new_rect)
    
    return collision

def min_distance_from_points(pos, points):
    min_dist = distance(pos, points[0])
    for p in points:
        dist = distance(pos, p)
        if min_dist > dist:
            min_dist = dist
    
    return min_dist

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
    
def get_bus_stop_name(bus_stop):
    name_split = bus_stop['name'].split('.')
    name = bus_stop['name']
        
    for n in name_split:
        # 주요 경유지 처리
        stn_match = re.search(r'(?:(?:지하철)?[1-9]호선|신분당선|공항철도)?(.+역)(?:[1-9]호선|환승센터)?(?:[0-9]+번(출구|승강장))?$', n)
        center_match = re.search(r'(광역환승센터|환승센터|환승센타|고속터미널|잠실종합운동장)$', n)
        
        if center_match:
            return n, True
        elif stn_match:
            stn_name = stn_match[1]
            stn_name = re.sub(r'\(.+\)역', '역', stn_name)
            
            return stn_name, True
            
    return name, False

def get_seoul_bus_stops(routeid):
    # 서울 버스 정류장 목록 조회
    params = {'serviceKey': key, 'busRouteId': routeid}
    
    route_api_res = requests.get('http://ws.bus.go.kr/api/rest/busRouteInfo/getStaionByRoute', params = params).text
    route_api_tree = elemtree.fromstring(route_api_res)

    api_err = int(route_api_tree.find('./msgHeader/headerCd').text)

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

def get_gyeonggi_bus_stops(routeid):
    # 경기 버스 정류장 목록 조회
    params = {'serviceKey': key, 'routeId': routeid}
    
    route_api_res = requests.get('http://apis.data.go.kr/6410000/busrouteservice/getBusRouteStationList', params = params, timeout = 20).text
    route_api_tree = elemtree.fromstring(route_api_res)

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

def get_busan_bus_stops(route_id, route_bims_id):
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
    
    bus_stop_items2 = route_api_tree2.findall('./body/items/item')
    for i in bus_stop_items2:
        if i.find('./rpoint').text == '1':
            bus_stops[int(i.find('./bstopidx').text) - 1]['is_trans'] = True
            break
    
    return bus_stops

def get_seoul_bus_type(routeid):
    # 서울 버스 노선정보 조회
    params = {'serviceKey': key, 'busRouteId': routeid}
    
    route_api_res = requests.get('http://ws.bus.go.kr/api/rest/busRouteInfo/getRouteInfo', params = params).text
    route_api_tree = elemtree.fromstring(route_api_res)

    api_err = route_api_tree.find('./msgHeader/headerCd').text

    if api_err != '0' and api_err != '4':
        raise ValueError(route_api_tree.find('./msgHeader/headerMsg').text)

    route_api_body = route_api_tree.find('./msgBody/itemList')
    route_info = {}
    
    route_info['type'] = int(route_api_body.find('./routeType').text)
    route_info['name'] = route_api_body.find('./busRouteNm').text
    route_info['start'] = route_api_body.find('./stStationNm').text
    route_info['end'] = route_api_body.find('./edStationNm').text
    
    return route_info

def get_gyeonggi_bus_type(routeid):
    # 경기 버스 노선정보 조회
    params = {'serviceKey': key, 'routeId': routeid}
    
    route_api_res = requests.get('http://apis.data.go.kr/6410000/busrouteservice/getBusRouteInfoItem', params = params, timeout = 20).text
    route_api_tree = elemtree.fromstring(route_api_res)

    api_err = route_api_tree.find('./msgHeader/resultCode').text

    if api_err != '0' and api_err != '4':
        raise ValueError(route_api_tree.find('./msgHeader/resultMessage').text)

    route_api_body = route_api_tree.find('./msgBody/busRouteInfoItem')
    route_info = {}
    
    route_info['type'] = int(route_api_body.find('./routeTypeCd').text)
    route_info['name'] = route_api_body.find('./routeName').text
    route_info['start'] = route_api_body.find('./startStationName').text
    route_info['end'] = route_api_body.find('./endStationName').text
    
    return route_info

def get_busan_bus_type(route_bims_id):
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

def get_seoul_bus_route(routeid):
    # 서울 버스 노선형상 조회
    params = {'serviceKey': key, 'busRouteId': routeid}
    
    route_api_res = requests.get('http://ws.bus.go.kr/api/rest/busRouteInfo/getRoutePath', params = params).text
    route_api_tree = elemtree.fromstring(route_api_res)

    api_err = route_api_tree.find('./msgHeader/headerCd').text

    if api_err != '0' and api_err != '4':
        raise ValueError(route_api_tree.find('./msgHeader/headerMsg').text)

    route_api_body = route_api_tree.find('./msgBody')
    xml_route_positions = route_api_body.findall('./itemList')

    route_positions = []

    for i in xml_route_positions:
        x = float(i.find('./gpsX').text)
        y = float(i.find('./gpsY').text)
        
        route_positions.append((x, y))
    
    return route_positions

def get_gyeonggi_bus_route(routeid):
    # 경기 버스 노선형상 조회
    params = {'serviceKey': key, 'routeId': routeid}
    
    route_api_res = requests.get('http://apis.data.go.kr/6410000/busrouteservice/getBusRouteLineList', params = params, timeout = 20).text
    route_api_tree = elemtree.fromstring(route_api_res)

    api_err = route_api_tree.find('./msgHeader/resultCode').text

    if api_err != '0' and api_err != '4':
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

def search_seoul_bus_info(number):
    params = {'serviceKey': key, 'strSrch': number}
    
    list_api_res = requests.get('http://ws.bus.go.kr/api/rest/busRouteInfo/getBusRouteList', params = params).text
    list_api_tree = elemtree.fromstring(list_api_res)

    api_err = int(list_api_tree.find('./msgHeader/headerCd').text)

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

def search_gyeonggi_bus_info(number):
    bus_info_list = []
    
    try:
        params = {'serviceKey': key, 'keyword': number}
        
        list_api_res = requests.get('http://apis.data.go.kr/6410000/busrouteservice/getBusRouteList', params = params, timeout = 20).text
        list_api_tree = elemtree.fromstring(list_api_res)
        
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

def search_busan_bus_info(number):
    bus_info_list = []
    params = {'serviceKey': key, 'lineno': number}
    
    list_api_res = requests.get('http://apis.data.go.kr/6260000/BusanBIMS/busInfo', params = params).text
    list_api_tree = elemtree.fromstring(list_api_res)
    
    api_common_err = list_api_tree.find('./cmmMsgHeader/returnAuthMsg')
    if api_common_err:
        raise ValueError(api_common_err.text)
    
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

def search_bus_info(number):
    bus_info_list = []
    
    # 서울 버스 조회
    try:
        bus_info_list += search_seoul_bus_info(number)
    except Exception as e:
        print('서울 버스 정보를 조회하는 중 오류가 발생했습니다: ' + str(e))
    
    # 경기 버스 조회
    try:
        bus_info_list += search_gyeonggi_bus_info(number)
    except Exception as e:
        print('경기 버스 정보를 조회하는 중 오류가 발생했습니다: ' + str(e))
    
    # 부산 버스 조회
    try:
        bus_info_list += search_busan_bus_info(number)
    except Exception as e:
        print('부산 버스 정보를 조회하는 중 오류가 발생했습니다: ' + str(e))
        
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
    
    return sorted(bus_info_list, key=search_score)

def get_naver_map(left, top, right, bottom, naver_key_id, naver_key):
    route_size = ((right - left), (bottom - top))
    route_size_max = max(route_size[0], route_size[1])
    pos = ((left + right) / 2, (top + bottom) / 2)
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

def get_mapbox_map(left, top, right, bottom, mapbox_key, mapbox_style):
    route_size_max = max(right - left, bottom - top)
    level = 12
    
    while 2 ** (21 - level) > route_size_max and level < 14:
        level += 1
    
    tile_size = 2 ** (21 - level)
    
    gps_pos = convert_gps((left, top))
    tile_x1, tile_y1 = mapbox.deg2num(gps_pos[1], gps_pos[0], level)
    
    gps_pos = convert_gps((right, bottom))
    tile_x2, tile_y2 = mapbox.deg2num(gps_pos[1], gps_pos[0], level)
    
    result = '<g id="background-map">\n'
    
    tile_pos = mapbox.num2deg(tile_x1, tile_y1, level)
    pos_x1, pos_y1 = convert_pos((tile_pos[1], tile_pos[0]))
    
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    
    for x in range(tile_x1, tile_x2 + 1):
        for y in range(tile_y1, tile_y2 + 1):
            cache_filename = cache_dir + '/tile{}-{}-z{}.svg'.format(x, y, level)
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

def main():
    parser = argparse.ArgumentParser(prog='bus_routemap')
    parser.add_argument('search_query')
    parser.add_argument('--style', choices=['light', 'dark'], default='light', required=False)
    
    try:
        with open('key.json', mode='r', encoding='utf-8') as key_file:
            global key, naver_key_id, naver_key
            key_json = json.load(key_file)
            key = key_json['bus_api_key']
            naver_key_id = key_json['naver_api_key_id']
            naver_key = key_json['naver_api_key']
            mapbox_key = key_json['mapbox_key']
    except FileNotFoundError:
        with open('key.json', mode='w', encoding='utf-8') as key_file:
            key_json = {'bus_api_key': '', 'naver_api_key_id': '', 'naver_api_key': '', 'mapbox_key': ''}
            json.dump(key_json, key_file, indent=4)
        
        print('각 지자체에 해당하는 버스 API 키를 발급받아 key.json에 저장하십시오.')
        print('서울시 API: https://www.data.go.kr/data/15000193/openapi.do')
        print('경기도 API: https://www.data.go.kr/data/15080662/openapi.do')
        print('부산시 API: https://www.data.go.kr/data/15092750/openapi.do')
        return
    
    args = parser.parse_args()
    
    if not args.search_query:
        query = input('검색어: ')
    else:
        query = args.search_query
    
    if args.style == 'light':
        mapbox_style = 'kiwitree/clinp1vgh002t01q4c2366q3o'
    elif args.style == 'dark':
        mapbox_style = 'kiwitree/clirdaqpr00hu01pu8t7vhmq7'
    
    bus_info_list = search_bus_info(query)
    bus_index = None
    
    if len(bus_info_list) == 0:
        print('검색 결과 없음')
        return
    
    i = 0
    while i < len(bus_info_list):
        bus = bus_info_list[i]
        print('{}. [{}] {}({})'.format(i+1, route_type_str[bus['type']], bus['name'], bus['desc']))
        
        i += 1
        if i % 20 == 0 or i == len(bus_info_list):
            bus_index = input('불러올 노선을 선택하세요: ')
            if bus_index:
                break
    
    if not bus_index:
        return
    
    try:
        bus_index = int(bus_index)
        if bus_index < 1 or bus_index > len(bus_info_list):
            return
        route_data = bus_info_list[bus_index - 1]
    except ValueError:
        return
    
    print('노선 정보 불러오는 중...')
    try:
        if route_data['type'] <= 10:
            bus_stops = get_seoul_bus_stops(route_data['id'])
            route_positions = get_seoul_bus_route(route_data['id'])
            route_info = get_seoul_bus_type(route_data['id'])
        elif route_data['type'] <= 60:
            bus_stops = get_gyeonggi_bus_stops(route_data['id'])
            route_positions = get_gyeonggi_bus_route(route_data['id'])
            route_info = get_gyeonggi_bus_type(route_data['id'])
        else:
            route_positions, route_bims_id = get_busan_bus_route(route_data['name'])
            bus_stops = get_busan_bus_stops(route_data['id'], route_bims_id)
            route_info = get_busan_bus_type(route_bims_id)
    except requests.exceptions.ConnectTimeout:
        print('Request Timeout')
        return
    
    print('노선도 렌더링 중...')
    
    is_one_way = False
    draw_full_svg = True
    draw_background_map = True

    points = []

    for pos in route_positions:
        points.append(convert_pos(pos))
    
    route_left = points[0][0]
    route_right = points[0][0]
    route_top = points[0][1]
    route_bottom = points[0][1]
    
    for pos in points:
        if route_left > pos[0]:
            route_left = pos[0]
        elif route_right < pos[0]:
            route_right = pos[0]
        
        if route_top > pos[1]:
            route_top = pos[1]
        elif route_bottom < pos[1]:
            route_bottom = pos[1]
    
    route_size = (route_right - route_left, route_bottom - route_top)
    
    mapframe_left = route_left
    mapframe_right = route_right
    mapframe_top = route_top
    mapframe_bottom = route_bottom
    
    if route_size[0] < route_size[1] / 1.5:
        route_size = (route_size[1] / 1.5, route_size[1])
    elif route_size[1] < route_size[0] / 1.5:
        route_size = (route_size[0], route_size[0] / 1.5)
    
    size_factor = route_size[0] / 640
    min_interval = 60 * size_factor
    
    # 일방통행 여부 묻기
    if distance(points[0], points[-1]) > 50:
        input_one_way = None
        while input_one_way != 'Y' and input_one_way != 'N':
            input_one_way = input('일방통행 노선으로 처리(Y/N): ').upper()
        
        if input_one_way == 'Y':
            is_one_way = True
    
    style_path_base = "display:inline;fill:none;stroke-width:{};stroke-linecap:round;stroke-linejoin:round;stroke-miterlimit:4;stroke-dasharray:none;stroke-opacity:1".format(8 * size_factor)
    
    if route_info['type'] == 1 or route_info['type'] == 51:
        # 공항리무진
        line_color = '#aa9872'
        line_dark_color = '#81704e'
    elif route_info['type'] == 2 or route_info['type'] == 4 or route_info['type'] == 30:
        # 서울 지선
        line_color = '#5bb025'
        line_dark_color = '#44831c'
    elif route_info['type'] == 6 or route_info['type'] == 11 or route_info['type'] == 21:
        if route_info['name'][0] == 'P':
            # 경기 프리미엄
            line_color = '#aa9872'
            line_dark_color = '#81704e'
        else:
            # 서울 광역 / 경기 직좌
            line_color = '#c83737'
            line_dark_color = '#782121'
    elif route_info['type'] == 12 or route_info['type'] == 22:
        # 경기 일좌
        line_color = '#0075c8'
        line_dark_color = '#005693'
    elif route_info['type'] == 13 or route_info['type'] == 23:
        # 경기 일반
        line_color = '#248f6c'
        line_dark_color = '#19654b'
    elif route_info['type'] == 14:
        # 광역급행버스
        line_color = '#00aad4'
        line_dark_color = '#0088aa'
    elif route_info['type'] == 61:
        # 부산 일반
        line_color = '#3399ff'
        line_dark_color = '#2770b7'
    elif route_info['type'] == 62 or route_info['type'] == 63:
        # 부산 급행 / 좌석
        line_color = '#f58220'
        line_dark_color = '#b45708'
    elif route_info['type'] == 64:
        # 부산 심야
        line_color = '#aaaaaa'
        line_dark_color = '#747474'
    elif route_info['type'] == 65:
        # 부산 마을
        line_color = '#6EBF46'
        line_dark_color = '#559734'
    else:
        # 서울 간선
        line_color = '#3d5bab'
        line_dark_color = '#263c77'
    
    if args.style == 'light':
        page_color = '#ffffff'
    elif args.style == 'dark':
        page_color = '#282828'
    
    fill_color = '#ffffff'
    if route_info['name'][0] == 'N':
        fill_color = '#ffcc00'
    fill_color_gray = '#cccccc'
    
    style_path = "stroke:{};".format(line_color) + style_path_base
    style_path_dark = "stroke:{};".format(line_dark_color) + style_path_base
    
    style_circle_base = "opacity:1;fill-opacity:1;stroke-width:{};stroke-linecap:round;stroke-linejoin:round;stroke-miterlimit:4;stroke-dasharray:none;stroke-dashoffset:0;stroke-opacity:1;paint-order:normal".format(3.2 * size_factor)
    
    style_circle = "stroke:{};".format(line_color) + style_circle_base
    style_circle_dark = "stroke:{};".format(line_dark_color) + style_circle_base
    
    style_text = "font-size:30px;line-height:1.0;font-family:'KoPubDotum Bold';text-align:start;letter-spacing:0px;word-spacing:0px;fill-opacity:1;"
    
    if args.style == 'light':
        style_fill_circle = "fill:#ffffff;"
    elif args.style == 'dark':
        style_fill_circle = "fill:#282828;"
    
    style_fill_white = "fill:#ffffff;"
    style_fill_gray = "fill:#cccccc;"
    style_fill_yellow = "fill:#ffcc00;"
    
    svg_depot_icon = '<g id="bus_depot" transform="translate({0:.2f}, {1:.2f}) scale({2:.2f}, {2:.2f}), rotate({3:.2f})"><circle style="fill:{4};fill-opacity:1;stroke:nonel" cx="0" cy="0" r="5.8" /> <path style="fill:#ffffff;fill-opacity:1;stroke:none" d="m 0,0 c -0.19263,0 -0.3856,0.073 -0.5332,0.2207 -0.2952,0.2952 -0.2952,0.7712 0,1.0664 l 1.00976,1.0097 h -4.10742 c -0.41747,0 -0.75195,0.3365 -0.75195,0.7539 0,0.4175 0.33448,0.7539 0.75195,0.7539 h 4.11719 l -1.05469,1.0547 c -0.2952,0.2952 -0.2952,0.7712 0,1.0664 0.2952,0.2952 0.77121,0.2952 1.06641,0 l 2.25586,-2.2539 c 0.0305,-0.022 0.0603,-0.049 0.0879,-0.076 0.16605,-0.1661 0.23755,-0.3876 0.21679,-0.6036 -6.2e-4,-0.01 -10e-4,-0.013 -0.002,-0.019 -0.002,-0.018 -0.005,-0.035 -0.008,-0.053 -3.9e-4,0 -0.002,0 -0.002,-0.01 -0.0347,-0.1908 -0.14003,-0.3555 -0.28907,-0.4668 l -2.22461,-2.2265 c -0.1476,-0.1476 -0.34057,-0.2207 -0.5332,-0.2207 z" transform="translate(0.6,-3)" /></g>'
    
    svg = ''
    
    trans_id = None
    
    # 버스 정류장 렌더링
    bus_stop_name_list = []
    
    main_stop_list = []
    minor_stop_list = []
    
    # 중앙차로 정류장 괄호 제거
    rx_centerstop = re.compile('\(중\)$')
    rx_pass_stop = re.compile('\((경유|가상)\)$')
    for i in range(len(bus_stops)):
        match = rx_centerstop.search(bus_stops[i]['name'])
        if match:
            bus_stops[i]['name'] = bus_stops[i]['name'][:match.start(0)]
    
    # 기종점 처리
    for i in range(len(bus_stops)):
        if is_one_way:
            is_trans = i == len(bus_stops) - 1
        else:
            is_trans = bool(bus_stops[i]['is_trans'])
        
        if i == 0 or is_trans:
            name, is_main = get_bus_stop_name(bus_stops[i])
            bus_stop_name_list.append(name)
            
            pos = convert_pos(bus_stops[i]['pos'])
            pass_stop = bool(rx_pass_stop.search(bus_stops[i]['name']))
            
            main_stop_list.append({'ord': i, 'pos': pos, 'name': name, 'section': 0, 'pass': pass_stop})
        
        if is_trans:
            trans_id = i
            break
            
    t_point = find_nearest_point(convert_pos(bus_stops[trans_id]['pos']), points)
    
    # 주요 정류장 처리
    for i in range(len(bus_stops)):
        name, is_main = get_bus_stop_name(bus_stops[i])
        if not is_main or name in bus_stop_name_list:
            continue
        
        bus_stop_name_list.append(name)
        
        pos = convert_pos(bus_stops[i]['pos'])
        pass_stop = bool(rx_pass_stop.search(bus_stops[i]['name']))
        section = 1 if i > trans_id else 0
        
        if i > trans_id:
            min_path_dist = min_distance_from_points(pos, points[:t_point])
            if min_path_dist < min_interval / 8:
                section = 0
        
        main_stop_list.append({'ord': i, 'pos': pos, 'name': name, 'section': section, 'pass': pass_stop})
        
    main_stop_ids = [x['ord'] for x in main_stop_list]
    
    # 비주요 정류장 처리
    for i in range(len(bus_stops)):
        if i in main_stop_ids:
            continue
        
        pos = convert_pos(bus_stops[i]['pos'])
        pass_stop = bool(rx_pass_stop.search(bus_stops[i]['name']))
        section = 1 if i > trans_id else 0
        
        stop_points = [s['pos'] for s in main_stop_list + minor_stop_list]
        min_dist = min_distance_from_points(pos, stop_points)
        
        if i > trans_id:
            min_path_dist = min_distance_from_points(pos, points[:t_point])
            if min_path_dist < min_interval / 4:
                continue
        
        if min_dist > min_interval:
            minor_stop_list.append({'ord': i, 'pos': pos, 'name': bus_stops[i]['name'], 'section': section, 'pass': pass_stop})
    
    text_rects = []
    
    def draw_bus_stop(stop, type = 0):
        stop_circle_style = ((style_fill_gray if stop['pass'] else style_fill_circle) if route_info['name'][0] != 'N' else style_fill_yellow) + (style_circle if stop['section'] == 0 else style_circle_dark)
        svg_circle = '<circle style="{}" cx="{}" cy="{}" r="{}" />\n'.format(stop_circle_style, stop['pos'][0], stop['pos'][1], 6 * size_factor)
        
        if stop['section'] == 0:
            stop_p = find_nearest_point(stop['pos'], points[:t_point])
        else:
            stop_p = find_nearest_point(stop['pos'], points[t_point:]) + t_point
        
        stop_p_prev, stop_p_next = get_point_segment(points, stop_p, stop_p, 10 * size_factor)
        
        path_dir = (points[stop_p_next][0] - points[stop_p_prev][0], points[stop_p_next][1] - points[stop_p_prev][1])
        normal_dir = (path_dir[1], -path_dir[0])
        
        if normal_dir[0] == 0 and normal_dir[1] == 0:
            normal_dir = (1, 1)
        
        if normal_dir[0] < 0:
            normal_dir = (-normal_dir[0], -normal_dir[1])
        
        dir_factor = math.sqrt(normal_dir[0] ** 2 + normal_dir[1] ** 2)
        normal_dir = (normal_dir[0] / dir_factor, normal_dir[1] / dir_factor)
        
        # 정류장 명칭 박스 위치 설정
        text_size_factor = size_factor * (0.7 if type == 0 else 0.56)
        text_height = 30 * text_size_factor
        
        match = rx_pass_stop.search(stop['name'])
        if match:
            stop_name_main = stop['name'][:match.start(0)]
            stop_name_suffix = stop['name'][match.start(0):]
        else:
            stop_name_main = stop['name']
            stop_name_suffix = ''
        
        text_width = (get_text_width(stop_name_main) * 27.5 + get_text_width(stop_name_suffix) * 22 + 25)
        
        text_pos_right = (stop['pos'][0] + 20 * normal_dir[0] * size_factor,  stop['pos'][1] + 20 * normal_dir[1] * size_factor - text_height / 2)
        text_rect_right = (text_pos_right[0], text_pos_right[1], text_width * text_size_factor, text_height)
        
        text_pos_left = (stop['pos'][0] - 20 * normal_dir[0] * size_factor - text_width * text_size_factor, stop['pos'][1] - 20 * normal_dir[1] * size_factor - text_height / 2)
        text_rect_left = (text_pos_left[0], text_pos_left[1], text_width * text_size_factor, text_height)
        
        if normal_dir[1] < 0:
            normal_dir = (-normal_dir[0], -normal_dir[1])
        
        text_pos_up = (stop['pos'][0] + 20 * normal_dir[0] * size_factor - text_width * text_size_factor / 2, stop['pos'][1] + 20 * normal_dir[1] * size_factor - text_height / 2)
        text_rect_up = (text_pos_up[0], text_pos_up[1], text_width * text_size_factor, text_height)
        
        text_pos_down = (stop['pos'][0] - 20 * normal_dir[0] * size_factor - text_width * text_size_factor / 2, stop['pos'][1] - 20 * normal_dir[1] * size_factor - text_height / 2)
        text_rect_down = (text_pos_down[0], text_pos_down[1], text_width * text_size_factor, text_height)
        
        text_pos_list = [text_pos_up, text_pos_down, text_pos_left, text_pos_right]
        text_rect_list = [text_rect_up, text_rect_down, text_rect_left, text_rect_right]
        collisions = [get_collision_score(x, text_rects, points) for x in text_rect_list]
        min_col = 0
        
        for i in range(1, len(collisions)):
            if collisions[min_col] >= collisions[i]:
                min_col = i
        
        text_pos = text_pos_list[min_col]
        text_rect = text_rect_list[min_col]
        
        text_rects.append(text_rect)
            
        stop_name_svg = stop_name_main.replace('&', '&amp;')
        if stop_name_suffix:
            stop_name_svg += '<tspan style="font-size:24px">{}</tspan>'.format(stop_name_suffix)
        
        svg_text = '<rect style="fill:{};fill-opacity:1;stroke:none;" width="{:.2f}" height="36" x="0" y="0" ry="18" />'.format(line_color if stop['section'] == 0 else line_dark_color, text_width)
        svg_text += '<text style="{}" text-anchor="middle" x="{:.2f}" y="28">{}</text>\n'.format(style_text + (style_fill_gray if stop['pass'] else style_fill_white), text_width / 2, stop_name_svg)
        svg_text = '<g id="stop{3}" transform="translate({0:.2f}, {1:.2f}) scale({2:.2f}, {2:.2f})">'.format(text_pos[0], text_pos[1], text_size_factor, stop['ord']) + svg_text + '</g>'
        
        # update mapframe
        nonlocal mapframe_left, mapframe_right, mapframe_top, mapframe_bottom
        if mapframe_right < text_rect[0] + text_rect[2]:
            mapframe_right = text_rect[0] + text_rect[2]
        if mapframe_left > text_rect[0]:
            mapframe_left = text_rect[0]
        if mapframe_bottom < text_rect[1] + text_rect[3]:
            mapframe_bottom = text_rect[1] + text_rect[3]
        if mapframe_top > text_rect[1]:
            mapframe_top = text_rect[1]
        
        # 기점 표시
        if stop['ord'] == 0:
            dir_len = math.sqrt(path_dir[0] ** 2 + path_dir[1] ** 2)
            
            if dir_len == 0:
                dir_cos = 1
            else:
                dir_cos = path_dir[0] / dir_len
            
            dir_deg = math.acos(dir_cos) / math.pi * 180
            
            if path_dir[1] < 0:
                dir_deg = 360 - dir_deg
                
            svg_text += svg_depot_icon.format(stop['pos'][0] + 20 * normal_dir[0] * size_factor, stop['pos'][1] + 20 * normal_dir[1] * size_factor, size_factor * 1.5, dir_deg, line_color) + '\n'
            
        return svg_circle + svg_text
    
    def draw_bus_info():
        name_match = re.search('[0-9A-Za-z]+', route_info['name'])
        if name_match:
            bus_name_main = route_info['name'][:name_match.end(0)]
            bus_name_suffix = route_info['name'][name_match.end(0):]
        else:
            bus_name_main = route_info['name']
            bus_name_suffix = ''
            
        bus_name_width = get_text_width(bus_name_main) * 72 + get_text_width(bus_name_suffix) * 60 + 45
        bus_startend_width = (get_text_width(route_info['start']) + get_text_width(route_info['end'])) * 57 + 150
        
        pos_x = route_left
        pos_y = route_top
        
        for text_rect in text_rects:
            if text_rect[0] < pos_x:
                pos_x = text_rect[0]
                
            if text_rect[1] < pos_y:
                pos_y = text_rect[1]
        
        pos_y -= 100 * size_factor * 0.8
        
        # update mapframe
        nonlocal mapframe_left, mapframe_right, mapframe_top, mapframe_bottom
        mapframe_top = pos_y
        
        bus_name_svg = bus_name_main + '<tspan style="font-size:72px">{}</tspan>'.format(bus_name_suffix)
        if bus_name_main[0] == 'N':
            bus_name_svg = '<tspan style="fill:#ffcc00">N</tspan>' + bus_name_svg[1:]
        
        svg_text = '<g id="businfo" transform="translate({0}, {1}) scale({2}, {2})" style="display:inline">'.format(pos_x, pos_y, size_factor * 0.75)
        svg_text += '<rect y="0" x="0" height="100" width="{}" id="busname_bg" style="opacity:1;fill:{};fill-opacity:1;stroke:none;" />'.format(bus_name_width, line_color)
        svg_text += '<text id="busname" y="82" x="20" style="font-weight:normal;font-size:85.3333px;font-family:\'Din Medium\';text-align:start;fill:#ffffff">{}</text>'.format(bus_name_svg)
        svg_text += '<rect y="0" x="{}" height="100" width="{}" id="busstartend_bg" style="opacity:1;fill:#ffffff;fill-opacity:1;stroke:none;" />'.format(bus_name_width, bus_startend_width)
        svg_text += '<text id="busstartend" y="70" x="{}" style="font-weight:bold;font-size:64px;font-family:\'NanumSquare\';text-align:start;fill:#000000">{} <tspan style="font-family:\'NanumSquareRound\'">↔</tspan> {}</text>'.format(bus_name_width + 20, route_info['start'], route_info['end'])
        svg_text += '</g>'
        
        return svg_text
    
    for stop in main_stop_list:
        # svg += draw_bus_stop(stop, 0)
        svg += draw_bus_stop(stop, 1)
    
    for stop in minor_stop_list:
        svg += draw_bus_stop(stop, 1)
    
    # 노선 경로 렌더링
    path_points = []
    
    path_points.append(points[:t_point+1])
    path_points.append(points[t_point:])
    
    if route_info['type'] <= 10:
        # skip = 2
        skip = 1
    else:
        skip = 1
    
    svg_path = ''
    
    is_path_dark = False
    skip_threshold = 5 * size_factor
    
    dark_segments = []
    
    segment_start = 0
    segment_end = -1
    
    for i in range(len(path_points[1])):
        min_dist = 10000
        for j in range(len(path_points[0]) - 1):
            new_dist = distance_from_segment(path_points[1][i], path_points[0][j], path_points[0][j+1])
            if min_dist > new_dist:
                min_dist = new_dist
        
        if min_dist > skip_threshold and i != len(path_points[1]) - 1:
            # print(i, min_dist, path_points[1][i])
            if segment_end < 0:
                segment_start = i
            segment_end = i
        elif segment_end >= 0:
            dark_segments.append(get_point_segment(path_points[1], segment_start, segment_end, skip_threshold * 2))
            segment_end = -1
    
    # print(dark_segments)
    if len(dark_segments) == 0:
        dark_segments.append([0, 0])
    
    for p in path_points:
        svg_path_d = 'M {:.5f} {:.5f} '.format(p[0][0], p[0][1])
        segment_num = 0
        i = skip
        while i < len(p):
            if (i < dark_segments[segment_num][0] or i > dark_segments[segment_num][1]) and is_path_dark:
                svg_path_d += 'M {:.5f} {:.5f} '.format(p[i][0], p[i][1])
                if i > dark_segments[segment_num][1] and segment_num < len(dark_segments) - 1:
                    segment_num += 1
                i += 1
            else:
                svg_path_d += 'L {:.5f} {:.5f} '.format(p[i][0], p[i][1])
                i += skip

        if i >= dark_segments[segment_num][1] and is_path_dark:
            svg_path_d += 'M {:.5f} {:.5f} '.format(p[-1][0], p[-1][1])
        else:
            svg_path_d += 'L {:.5f} {:.5f} '.format(p[-1][0], p[-1][1])
            
        svg_path = '<path style="{}" d="{}" />\n'.format(style_path_dark if is_path_dark else style_path, svg_path_d) + svg_path
        is_path_dark = not is_one_way
    
    svg = svg_path + svg
        
    svg += draw_bus_info() + '\n'
    
    with open('bus.svg', mode='w+', encoding='utf-8') as f:
        if draw_full_svg:
            f.write('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n')
            f.write('<svg width="512" height="512" viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"><style></style>\n')
            f.write('<sodipodi:namedview id="namedview1" pagecolor="{}" bordercolor="#cccccc" borderopacity="1" inkscape:deskcolor="#e5e5e5"/>'.format(page_color))
        
        if draw_background_map:
            if mapbox_key:
                f.write(get_mapbox_map(mapframe_left - 10, mapframe_top - 10, mapframe_right + 10, mapframe_bottom + 10, mapbox_key, mapbox_style))
            elif naver_key_id and naver_key:
                f.write(get_naver_map(mapframe_left, mapframe_top, mapframe_right, mapframe_bottom, naver_key_id, naver_key))
            else:
                print('배경 지도를 사용하려면 API 키를 입력해야 합니다.')
        
        f.write(svg)
        
        if draw_full_svg:
            f.write('</svg>')
        
        print('처리 완료')

if __name__ == '__main__':
    main()