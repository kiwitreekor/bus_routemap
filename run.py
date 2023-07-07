from datetime import datetime
import requests, time, sys, os, re, math, json, base64, argparse, urllib
import bus_api
from routemap import *

key = ''
naver_key_id = ''
naver_key = ''

def main():
    parser = argparse.ArgumentParser(prog='bus_routemap')
    parser.add_argument('search_query')
    parser.add_argument('--style', choices=['light', 'dark'], default='light', required=False)
    
    try:
        with open('key.json', mode='r', encoding='utf-8') as key_file:
            global key, naver_key_id, naver_key
            key_json = json.load(key_file)
            key = key_json['bus_api_key']
            # naver_key_id = key_json['naver_api_key_id']
            # naver_key = key_json['naver_api_key']
            mapbox_key = key_json['mapbox_key']
    except FileNotFoundError:
        with open('key.json', mode='w', encoding='utf-8') as key_file:
            # key_json = {'bus_api_key': '', 'naver_api_key_id': '', 'naver_api_key': '', 'mapbox_key': ''}
            key_json = {'bus_api_key': '', 'mapbox_key': ''}
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
    
    bus_info_list, error = bus_api.search_bus_info(key, query, return_error = True)
    if error:
        print(str(error))
    bus_index = None
    
    if len(bus_info_list) == 0:
        print('검색 결과 없음')
        return
    
    i = 0
    while i < len(bus_info_list):
        bus = bus_info_list[i]
        print('{}. [{}] {}({})'.format(i+1, bus_api.route_type_str[bus['type']], bus['name'], bus['desc']))
        
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
            bus_stops = bus_api.get_seoul_bus_stops(key, route_data['id'])
            route_positions = bus_api.get_seoul_bus_route(key, route_data['id'])
            route_info = bus_api.get_seoul_bus_type(key, route_data['id'])
        elif route_data['type'] <= 60:
            bus_stops = bus_api.get_gyeonggi_bus_stops(key, route_data['id'])
            route_positions = bus_api.get_gyeonggi_bus_route(key, route_data['id'])
            route_info = bus_api.get_gyeonggi_bus_type(key, route_data['id'])
        else:
            route_positions, route_bims_id = bus_api.get_busan_bus_route(route_data['name'])
            bus_stops = bus_api.get_busan_bus_stops(key, route_data['id'], route_bims_id)
            route_info = bus_api.get_busan_bus_type(key, route_bims_id)
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
    
    # 일방통행 여부 묻기
    if distance(points[0], points[-1]) > 50:
        input_one_way = None
        while input_one_way != 'Y' and input_one_way != 'N':
            input_one_way = input('일방통행 노선으로 처리(Y/N): ').upper()
        
        if input_one_way == 'Y':
            is_one_way = True
    
    routemap = RouteMap(route_info, bus_stops, points, is_one_way = is_one_way, theme = args.style)
    
    route_size = routemap.mapframe.size()
    
    if route_size[0] < route_size[1] / 1.5:
        route_size = (route_size[1] / 1.5, route_size[1])
    elif route_size[1] < route_size[0] / 1.5:
        route_size = (route_size[0], route_size[0] / 1.5)
    
    size_factor = route_size[0] / 640
    min_interval = 60 * size_factor
    
    svg = routemap.render(size_factor, min_interval)
    
    routemap.mapframe.extend(10)
    
    if args.style == 'light':
        mapbox_style = 'kiwitree/clinp1vgh002t01q4c2366q3o'
        page_color = '#ffffff'
    elif args.style == 'dark':
        mapbox_style = 'kiwitree/clirdaqpr00hu01pu8t7vhmq7'
        page_color = '#282828'
    
    with open('bus.svg', mode='w+', encoding='utf-8') as f:
        if draw_full_svg:
            f.write('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n')
            f.write('<svg width="512" height="512" viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"><style></style>\n')
            f.write('<sodipodi:namedview id="namedview1" pagecolor="{}" bordercolor="#cccccc" borderopacity="1" inkscape:deskcolor="#e5e5e5"/>'.format(page_color))
        
        if draw_background_map:
            if mapbox_key:
                f.write(bus_api.get_mapbox_map(routemap.mapframe, mapbox_key, mapbox_style))
            elif naver_key_id and naver_key:
                f.write(bus_api.get_naver_map(routemap.mapframe, naver_key_id, naver_key))
            else:
                print('배경 지도를 사용하려면 API 키를 입력해야 합니다.')
        
        f.write(svg)
        
        if draw_full_svg:
            f.write('</svg>')
        
        print('처리 완료')

if __name__ == '__main__':
    main()