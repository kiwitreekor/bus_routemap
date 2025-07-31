import re, math, html
from PIL import ImageFont
from matplotlib import font_manager

origin_tile = (3490, 1584)

rx_pass_stop = re.compile('\((경유|가상)\)$')
rx_centerstop = re.compile('\(중\)$')

svg_depot_icon = '<g id="bus_depot" transform="translate(18, 18) scale(2.8, 2.8) rotate({0:.2f})"><circle style="fill:{1};fill-opacity:1;stroke:nonel" cx="0" cy="0" r="5.8" /> <path style="fill:#ffffff;fill-opacity:1;stroke:none" d="m 0,0 c -0.19263,0 -0.3856,0.073 -0.5332,0.2207 -0.2952,0.2952 -0.2952,0.7712 0,1.0664 l 1.00976,1.0097 h -4.10742 c -0.41747,0 -0.75195,0.3365 -0.75195,0.7539 0,0.4175 0.33448,0.7539 0.75195,0.7539 h 4.11719 l -1.05469,1.0547 c -0.2952,0.2952 -0.2952,0.7712 0,1.0664 0.2952,0.2952 0.77121,0.2952 1.06641,0 l 2.25586,-2.2539 c 0.0305,-0.022 0.0603,-0.049 0.0879,-0.076 0.16605,-0.1661 0.23755,-0.3876 0.21679,-0.6036 -6.2e-4,-0.01 -10e-4,-0.013 -0.002,-0.019 -0.002,-0.018 -0.005,-0.035 -0.008,-0.053 -3.9e-4,0 -0.002,0 -0.002,-0.01 -0.0347,-0.1908 -0.14003,-0.3555 -0.28907,-0.4668 l -2.22461,-2.2265 c -0.1476,-0.1476 -0.34057,-0.2207 -0.5332,-0.2207 z" transform="translate(0.6,-3)" /></g>'

class Mapframe():
    def __init__(self, left, top, right, bottom):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom
        
        if self.left > self.right:
            raise ValueError("left is greater than right")
        if self.top > self.bottom:
            raise ValueError("top is greater than bottom")
    
    def size(self):
        return (self.right - self.left, self.bottom - self.top)
    
    def width(self):
        return self.right - self.left
    
    def height(self):
        return self.bottom - self.top
    
    def update_rect(self, rect):
        if self.right < rect[0] + rect[2]:
            self.right = rect[0] + rect[2]
        if self.left > rect[0]:
            self.left = rect[0]
        if self.bottom < rect[1] + rect[3]:
            self.bottom = rect[1] + rect[3]
        if self.top > rect[1]:
            self.top = rect[1]
    
    def update_x(self, x):
        if self.right < x:
            self.right = x
        elif self.left > x:
            self.left = x
    
    def update_y(self, y):
        if self.bottom < y:
            self.bottom = y
        elif self.top > y:
            self.top = y
    
    def extend(self, x):
        self.left -= x
        self.right += x
        self.top -= x
        self.bottom += x
    
    def center(self):
        return ((self.left + self.right) / 2, (self.top + self.bottom) / 2)
    
    @classmethod
    def from_points(cls, points):
        left = min(x for x, _ in points)
        right = max(x for x, _ in points)
        top = min(y for _, y in points)
        bottom = max(y for _, y in points)
        
        return cls(left, top, right, bottom)

def escape_svg_text(text: str) -> str:
    escaped = html.escape(text, quote=True)
    escaped = escaped.replace("'", "&apos;")
    return escaped

def make_svg_path(style, points):
    path = "M"
    
    for i, (x, y) in enumerate(points):
        if i == 0:
            path += "{:.5f},{:.5f}".format(x, y)
        else:
            path += " L{:.5f},{:.5f}".format(x, y)
        
    return '<path style="{}" d="{}" />\n'.format(style, path)

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

def find_font_file(font_style):
    fp = font_manager.FontProperties(**font_style)  
    font_path = font_manager.findfont(fp, fallback_to_default=False)

    return font_path
    
def get_text_width(text, font_style):
    font_file = find_font_file(font_style)

    if font_file:
        font = ImageFont.truetype(font_file, 72)
        if font:
            return font.getlength(text) / 72
    
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
        collision += 4 * check_collision((p[0] - 2, p[1] - 2, 4, 4), new_rect)
    
    return collision

def min_distance_from_points(pos, points):
    min_dist = distance(pos, points[0])
    for p in points:
        dist = distance(pos, p)
        if min_dist > dist:
            min_dist = dist
    
    return min_dist

def min_distance_from_segments(pos, points):
    min_dist = distance(pos, points[0])
    for i in range(len(points) - 1):
        dist = distance_from_segment(pos, points[i], points[i+1])
        if min_dist > dist:
            min_dist = dist
    
    return min_dist

def get_bus_stop_name(bus_stop):
    if bus_stop['name'] == '4.19민주묘지역': # 역명에 마침표가 있는 유일한 경우
        return '4.19민주묘지역', True
    
    name_split = bus_stop['name'].split('.')
    name = bus_stop['name']
    
    # 중앙차로 정류장 괄호 제거
    match = rx_centerstop.search(bus_stop['name'])
    if match:
        name = name[:match.start(0)]
        
    for n in name_split:
        # 주요 경유지 처리
        stn_match = re.search(r'(?:(?:지하철)?[1-9]호선|신분당선|공항철도)?(.+역)(?:[1-9]호선|환승센터|환승센타)?(?:[0-9]+번(출구|승강장))?$', n)
        center_match = re.search(r'(광역환승센터|환승센터|환승센타|고속터미널|잠실종합운동장)$', n)
        
        if center_match:
            n = n.replace('환승센타', '환승센터')
            return n, True
        elif stn_match:
            stn_name = stn_match[1]
            stn_name = re.sub(r'\(.+\)역', '역', stn_name)
            
            return stn_name, True
            
    return name, False

def get_bus_color(route_info):
    if route_info['type'] == 1 or route_info['type'] == 51:
        # 공항리무진
        line_color = '#aa9872'
        line_dark_color = '#81704e'
    elif route_info['type'] == 2 or route_info['type'] == 4:
        # 서울 지선
        line_color = '#5bb025'
        line_dark_color = '#44831c'
    elif route_info['type'] == 5:
        # 서울 순환
        line_color = '#f99d1c'
        line_dark_color = '#b46c0f'
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
    elif route_info['type'] == 30:
        # 경기 마을
        line_color = '#f2a900'
        line_dark_color = '#b57c00'
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
    
    return (line_color, line_dark_color)

class RouteMap():
    def __init__(self, route_info, bus_stops, points, is_one_way = False, theme = 'light'):
        self.route_info = route_info
        self.bus_stops = bus_stops
        self.points = points
        
        self.is_one_way = is_one_way
        self.mapframe = Mapframe.from_points(self.points)
        
        self.update_trans_id(self.get_trans_id())
        self.line_color, self.line_dark_color = get_bus_color(self.route_info)
        self.theme = theme

    def get_trans_id(self):
        for i, stop in enumerate(self.bus_stops):
            if stop['is_trans']:
                return i
        
        return None
    
    def update_trans_id(self, new_id):
        if new_id >= len(self.bus_stops) or new_id < 0:
            raise ValueError()
        
        self.trans_id = new_id
        self.t_point = find_nearest_point(convert_pos(self.bus_stops[self.trans_id]['pos']), self.points)

    def parse_bus_stops(self, min_interval):
        # 버스 정류장 렌더링
        bus_stop_name_list = []
        
        main_stop_list = []
        minor_stop_list = []
        
        last_stop_id = len(self.bus_stops) - 1 if self.is_one_way else self.trans_id
        
        # 기종점 처리
        for i in [0, last_stop_id]:
            name, is_main = get_bus_stop_name(self.bus_stops[i])
            bus_stop_name_list.append(name)
            
            pos = convert_pos(self.bus_stops[i]['pos'])
            pass_stop = bool(rx_pass_stop.search(self.bus_stops[i]['name']))
            section = 1 if i > self.trans_id else 0
            
            main_stop_list.append({'ord': i, 'pos': pos, 'name': name, 'section': section, 'pass': pass_stop})
        
        # 주요 정류장 처리
        for i in range(len(self.bus_stops)):
            name, is_main = get_bus_stop_name(self.bus_stops[i])
            if not is_main or name in bus_stop_name_list:
                continue
            
            bus_stop_name_list.append(name)
            
            pos = convert_pos(self.bus_stops[i]['pos'])
            pass_stop = bool(rx_pass_stop.search(self.bus_stops[i]['name']))
            section = 1 if i > self.trans_id else 0
            
            if section == 1:
                min_path_dist = min_distance_from_segments(pos, self.points[:self.t_point])
                if min_path_dist < min_interval / 8:
                    section = 0
            
            main_stop_list.append({'ord': i, 'pos': pos, 'name': name, 'section': section, 'pass': pass_stop})
            
        main_stop_ids = [x['ord'] for x in main_stop_list]
    
        # 비주요 정류장 처리
        for i in range(len(self.bus_stops)):
            if i in main_stop_ids:
                continue
            
            pos = convert_pos(self.bus_stops[i]['pos'])
            pass_stop = bool(rx_pass_stop.search(self.bus_stops[i]['name']))
            section = 1 if i > self.trans_id else 0
            
            stop_points = [s['pos'] for s in main_stop_list + minor_stop_list]
            min_dist = min_distance_from_points(pos, stop_points)
            
            if i > self.trans_id:
                min_path_dist = min_distance_from_segments(pos, self.points[:self.t_point])
                if min_path_dist < min_interval / 4:
                    continue
            
            if min_dist > min_interval:
                minor_stop_list.append({'ord': i, 'pos': pos, 'name': self.bus_stops[i]['name'], 'section': section, 'pass': pass_stop})
        
        return main_stop_list + minor_stop_list

    def get_bus_name(self):
        name_match = re.search(r'[0-9A-Za-z]+', self.route_info['name'])
        if name_match:
            bus_name_main = self.route_info['name'][:name_match.end(0)]
            bus_name_suffix = self.route_info['name'][name_match.end(0):]
        else:
            bus_name_main = self.route_info['name']
            bus_name_suffix = ''
        
        return bus_name_main, bus_name_suffix

    def draw_bus_info(self, size_factor):
        bus_name_main, bus_name_suffix = self.get_bus_name()
        bus_name_main_svg = ''
        bus_name_main_split = re.findall(r'[가-힣]+|N|[^가-힣]+', bus_name_main)
        bus_name_main_x = 0

        for i in range(len(bus_name_main_split)):
            if re.match(r'[가-힣]', bus_name_main_split[i]):
                bus_name_main_svg += '<text y="75" x="{}" style="font-weight:bold;font-size:72px;font-family:\'NanumSquare\';text-align:start;fill:#ffffff">{}</text>'.format(bus_name_main_x + 20, escape_svg_text(bus_name_main_split[i]))
                bus_name_main_x += get_text_width(bus_name_main_split[i], {'family': 'NanumSquare', 'weight': 'bold'}) * 72
            else:
                if bus_name_main_split[i] == 'N':
                    bus_name_main_svg += '<text y="82" x="{}" style="font-weight:normal;font-size:85.3333px;font-family:\'Din Medium\';text-align:start;fill:#ffcc00">{}</text>'.format(bus_name_main_x + 20, escape_svg_text(bus_name_main_split[i]))
                else:
                    bus_name_main_svg += '<text y="82" x="{}" style="font-weight:normal;font-size:85.3333px;font-family:\'Din Medium\';text-align:start;fill:#ffffff">{}</text>'.format(bus_name_main_x + 20, escape_svg_text(bus_name_main_split[i]))
                bus_name_main_x += get_text_width(bus_name_main_split[i], {'family': 'Din Medium'}) * 85.3333

        bus_name_svg = bus_name_main_svg + '<text y="82" x="{}" style="font-weight:normal;font-size:72px;font-family:\'Din Medium\';text-align:start;fill:#ffffff">{}</text>'.format(bus_name_main_x + 20, escape_svg_text(bus_name_suffix))
        bus_name_main_x += get_text_width(bus_name_suffix, {'family': 'Din Medium'}) * 72

        bus_name_width = bus_name_main_x + 40
        bus_startend_width = (get_text_width(self.route_info['start'], {'family': 'NanumSquare'}) + get_text_width(self.route_info['end'], {'family': 'NanumSquare'})) * 64 + 135

        bus_info_width = (bus_name_width + bus_startend_width) * size_factor
        
        if self.mapframe.width() < bus_info_width:
            pos_x = self.mapframe.center()[0] - bus_info_width / 2
        else:
            pos_x = self.mapframe.left
        pos_y = self.mapframe.top
        
        pos_y -= 135 * size_factor
        
        self.mapframe.update_rect((pos_x, pos_y, bus_info_width, 100 * size_factor))
        
        svg_text = '<g id="businfo" transform="translate({0}, {1}) scale({2}, {2})" style="display:inline">'.format(pos_x, pos_y, size_factor)
        svg_text += '<rect y="0" x="0" height="100" width="{}" id="busname_bg" style="opacity:1;fill:{};fill-opacity:1;stroke:none;" />'.format(bus_name_width, self.line_color)
        svg_text += bus_name_svg
        svg_text += '<rect y="0" x="{}" height="100" width="{}" id="busstartend_bg" style="opacity:1;fill:#ffffff;fill-opacity:1;stroke:none;" />'.format(bus_name_width, bus_startend_width)
        svg_text += '<text id="busstartend" y="70" x="{}" style="font-weight:bold;font-size:64px;font-family:\'NanumSquare\';text-align:start;fill:#000000">{} <tspan style="font-family:\'NanumSquareRound\'">↔</tspan> {}</text>'.format(bus_name_width + 20, self.route_info['start'], self.route_info['end'])
        svg_text += '</g>'
        
        return svg_text

    def draw_bus_stop_circle(self, stop, size_factor):
        style_circle_base = "opacity:1;fill-opacity:1;stroke-width:{};stroke-dasharray:none;stroke-opacity:1;".format(3.2 * size_factor)
        if self.theme == 'light':
            style_fill_circle = "fill:#ffffff;"
        elif self.theme == 'dark':
            style_fill_circle = "fill:#282828;"
        style_fill_gray = "fill:#cccccc;"
        style_fill_yellow = "fill:#ffcc00;"
        style_circle = "stroke:{};".format(self.line_color) + style_circle_base
        style_circle_dark = "stroke:{};".format(self.line_dark_color) + style_circle_base
        
        section = 0 if stop['section'] == 0 or self.is_one_way else 1
        
        stop_circle_style = ((style_fill_gray if stop['pass'] else style_fill_circle) if self.route_info['name'][0] != 'N' else style_fill_yellow) + (style_circle if section == 0 else style_circle_dark)
        svg_circle = '<circle style="{}" cx="{}" cy="{}" r="{}" />\n'.format(stop_circle_style, stop['pos'][0], stop['pos'][1], 6 * size_factor)
        
        return svg_circle
    
    def draw_bus_stop_text(self, stop, size_factor, direction = -1):
        style_fill_white = "fill:#ffffff;"
        style_fill_gray = "fill:#cccccc;"
        style_text = "font-size:30px;line-height:1.0;font-family:'KoPubDotum Bold';text-align:start;letter-spacing:0px;word-spacing:0px;fill-opacity:1;"
        
        section = 0 if stop['section'] == 0 or self.is_one_way else 1
        
        if section == 0:
            stop_p = find_nearest_point(stop['pos'], self.points[:self.t_point])
        else:
            stop_p = find_nearest_point(stop['pos'], self.points[self.t_point:]) + self.t_point
        
        stop_p_prev, stop_p_next = get_point_segment(self.points, stop_p, stop_p, 10 * size_factor)
        
        path_dir = (self.points[stop_p_next][0] - self.points[stop_p_prev][0], self.points[stop_p_next][1] - self.points[stop_p_prev][1])
        normal_dir = (path_dir[1], -path_dir[0])
        
        if normal_dir[0] == 0 and normal_dir[1] == 0:
            normal_dir = (1, 1)
        
        if normal_dir[0] < 0:
            normal_dir = (-normal_dir[0], -normal_dir[1])
        
        dir_factor = math.sqrt(normal_dir[0] ** 2 + normal_dir[1] ** 2)
        normal_dir = (normal_dir[0] / dir_factor, normal_dir[1] / dir_factor)
        
        # 정류장 명칭 박스 위치 설정
        text_size_factor = size_factor * 0.56
        text_height = 30 * text_size_factor
        
        match = rx_pass_stop.search(stop['name'])
        if match:
            stop_name_main = stop['name'][:match.start(0)]
            stop_name_suffix = stop['name'][match.start(0):]
        else:
            stop_name_main = stop['name']
            stop_name_suffix = ''

        text_width = (get_text_width(stop_name_main, {'family': 'KoPubDotum', 'weight': 'bold'}) * 30 + get_text_width(stop_name_suffix, {'family': 'KoPubDotum', 'weight': 'bold'}) * 24 + 30)
        text_offset = 0

        if stop['ord'] == 0:
            text_offset = 40 * text_size_factor
        
        text_pos_right = (stop['pos'][0] + 16 * normal_dir[0] * size_factor,  stop['pos'][1] + 16 * normal_dir[1] * size_factor - text_height / 2)
        text_rect_right = (text_pos_right[0], text_pos_right[1], text_width * text_size_factor + text_offset, text_height)
        
        text_pos_left = (stop['pos'][0] - 16 * normal_dir[0] * size_factor - text_width * text_size_factor - text_offset, stop['pos'][1] - 16 * normal_dir[1] * size_factor - text_height / 2)
        text_rect_left = (text_pos_left[0], text_pos_left[1], text_width * text_size_factor + text_offset, text_height)

        if normal_dir[1] > 0:
            normal_dir = (-normal_dir[0], -normal_dir[1])
        
        text_pos_up = (stop['pos'][0] - text_width * text_size_factor / 2, stop['pos'][1] - 25 * size_factor - text_height / 2)
        text_rect_up = (text_pos_up[0], text_pos_up[1], text_width * text_size_factor, text_height)
        
        text_pos_down = (stop['pos'][0] - text_width * text_size_factor / 2, stop['pos'][1] + 25 * size_factor - text_height / 2)
        text_rect_down = (text_pos_down[0], text_pos_down[1], text_width * text_size_factor, text_height)
        
        text_pos_list = [text_pos_up, text_pos_down, text_pos_left, text_pos_right]
        text_rect_list = [text_rect_up, text_rect_down, text_rect_left, text_rect_right]
        
        if direction == -1:
            collisions = [get_collision_score(x, self.text_rects, self.points) for x in text_rect_list]

            if stop['ord'] == 0:
                direction = 2
                if collisions[2] >= collisions[3]:
                    direction = 3
            else:
                direction = 0
                
                for i in range(1, len(collisions)):
                    if collisions[direction] >= collisions[i]:
                        direction = i
        else:
            if direction >= len(text_rect_list) or direction < 0:
                raise IndexError()
            
        text_pos = text_pos_list[direction]
        text_rect = text_rect_list[direction]
        
        self.text_rects.append(text_rect)
            
        stop_name_svg = escape_svg_text(stop_name_main)
        if stop_name_suffix:
            stop_name_svg += '<tspan style="font-size:24px">{}</tspan>'.format(escape_svg_text(stop_name_suffix))
        
        svg_text = ''
        depot_text_offset = 0

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
            
            depot_offset = 0
            depot_text_offset = 40
            if direction == 2:
                depot_offset = text_width + 4
                depot_text_offset = 0

            svg_text += '<g id="bus_depot_icon" transform="translate({:.2f}, 0)">'.format(depot_offset)
            svg_text += svg_depot_icon.format(dir_deg, self.line_color)
            svg_text += '</g>\n'

        svg_text += '<rect style="fill:{};fill-opacity:1;stroke:none;" width="{:.2f}" height="36" x="{:.2f}" y="0" ry="18" />'.format(self.line_color if section == 0 else self.line_dark_color, text_width, depot_text_offset)
        svg_text += '<text style="{}" text-anchor="middle" x="{:.2f}" y="28">{}</text>\n'.format(style_text + (style_fill_gray if stop['pass'] else style_fill_white), text_width / 2 + depot_text_offset, stop_name_svg)

        svg_text = '<g id="stop{3}" transform="translate({0:.2f}, {1:.2f}) scale({2:.2f}, {2:.2f})">'.format(text_pos[0], text_pos[1], text_size_factor, stop['ord']) + svg_text + '</g>'
        
        self.mapframe.update_rect(text_rect)
            
        return svg_text
    
    def render_path(self, size_factor):
        # 노선 경로 렌더링
        style_path_base = "display:inline;fill:none;stroke-width:{};stroke-linecap:round;stroke-linejoin:round;stroke-miterlimit:4;stroke-dasharray:none;stroke-opacity:1".format(8 * size_factor)
        style_path = "stroke:{};".format(self.line_color) + style_path_base
        style_path_dark = "stroke:{};".format(self.line_dark_color) + style_path_base
        
        path_points = []
        
        start_point = find_nearest_point(convert_pos(self.bus_stops[0]['pos']), self.points[:self.t_point])
        end_point = find_nearest_point(convert_pos(self.bus_stops[-1]['pos']), self.points[self.t_point:]) + self.t_point
        
        path_points.append(self.points[start_point:self.t_point+1])
        
        if self.route_info['type'] <= 10:
            # skip = 2
            skip = 1
        else:
            skip = 1
        
        is_path_dark = False
        skip_threshold = 5 * size_factor
        
        segment_start = 0
        segment_end = -1
        
        for i in range(self.t_point, end_point):
            min_dist = min_distance_from_segments(self.points[i], path_points[0])
            if min_dist > skip_threshold and i < end_point - 1:
                if segment_end < 0:
                    segment_start = i
                segment_end = i
            elif segment_end >= 0:
                path_segment = get_point_segment(self.points, segment_start, segment_end, skip_threshold * 2)
                path_points.append(self.points[path_segment[0]:min(path_segment[1]+1, end_point)])
                segment_end = -1
        
        svg_path = ''
        
        for i, path in enumerate(path_points):
            if i == 0 or self.is_one_way:
                path_style = style_path
            else:
                path_style = style_path_dark
            
            svg_path = make_svg_path(path_style, path) + svg_path
        
        return svg_path
    
    def render_init(self):
        self.text_rects = []
    
    def render(self, size_factor, min_interval):
        self.render_init()
        svg = self.render_path(size_factor)
        
        bus_stops = self.parse_bus_stops(min_interval)
        for stop in bus_stops:
            svg += self.draw_bus_stop_circle(stop, size_factor)
            svg += self.draw_bus_stop_text(stop, size_factor)
        svg += self.draw_bus_info(size_factor * 0.75) + '\n'
        
        return svg