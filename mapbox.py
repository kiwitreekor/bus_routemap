import math, requests, json, re, io, colorsys, sys, os
import mapbox_vector_tile

tile_url = 'https://api.mapbox.com/v4/{}/{}/{}/{}.mvt'
style_url = 'https://api.mapbox.com/styles/v1/{}'
properties = {}

sprite_cache = {}

class MapBoxError(Exception):
    pass

def check_token_valid(token):
    response = requests.get(style_url.format(''), params = {'access_token': token})
    if response.status_code == 401:
        return False
    else:
        return True
    

def resource_path(relative_path):
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

def deg2num(lat_deg, lon_deg, zoom):
    lat_rad = math.radians(lat_deg)
    n = 1 << zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    
    return xtile, ytile

def num2deg(tile_x, tile_y, zoom):
    n = 1 << zoom
    lon_deg = tile_x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * tile_y / n)))
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg

def css_style(style):
    style_str = ''
    
    for key, value in style.items():
        style_str += '{}:{};'.format(key, value)
    
    return style_str

def rgb_to_hex(rgb):
    return '#{:02x}{:02x}{:02x}'.format(int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255))

def color_to_rgb(color):
    rx_hsl = re.compile(r'hsl\(\s*(\d+),\s*(\d+)%,\s*(\d+)%\s*\)')
    rx_hsla = re.compile(r'hsla\(\s*(\d+),\s*(\d+)%,\s*(\d+)%\s*,\s*[0-9.]+\)')
    rx_rgb = re.compile(r'rgb\(\s*(\d+),\s*(\d+),\s*(\d+)\s*\)')
    rx_hex = re.compile(r'#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')
    
    hsl_match = rx_hsl.match(color)
    if hsl_match:
        return colorsys.hls_to_rgb(int(hsl_match[1])/360, int(hsl_match[3])/100, int(hsl_match[2])/100)
    
    hsla_match = rx_hsla.match(color)
    if hsla_match:
        return colorsys.hls_to_rgb(int(hsla_match[1])/360, int(hsla_match[3])/100, int(hsla_match[2])/100)
    
    hex_match = rx_hex.match(color)
    if hex_match:
        if len(color) == 4:
            return (int(color[1], 16)/15, int(color[2], 16)/15, int(color[3], 16)/15)
        else:
            return (int(color[1:3], 16)/255, int(color[3:5], 16)/255, int(color[5:7], 16)/255)
    
    rgb_match = rx_rgb.match(color)
    if rgb_match:
        return (int(rgb_match[1]) / 255, int(rgb_match[2]) / 255, int(rgb_match[3]) / 255)
    
    raise ValueError('Unknown Color: "{}"'.format(color))

def color_to_hex(color):
    return rgb_to_hex(color_to_rgb(color))

def interpolate_color(expression, method, input_value, feature):
    if len(expression) % 2 != 0:
        raise ValueError()
    
    color_list = []
    value_list = []
    
    for i in range(0, len(expression), 2):
        color_list.append(expression[i+1])
        value_list.append(expression[i])
    
    rgbs = []
    result = None
    
    for color in color_list:
        rgbs.append(color_to_rgb(color))
    
    for i in range(len(value_list)):
        if input_value < value_list[i]:
            return rgb_to_hex(rgbs[i])
    
    return rgb_to_hex(rgbs[-1])
    
    # todo: implement color interpolation

def interpolate(expression, method, input_value, feature):
    if len(expression) % 2 != 0:
        raise ValueError()
    
    value = get_value(input_value, feature)
    
    if value < expression[0]:
        return get_value(expression[1], feature)
    
    if value >= expression[-2]:
        return get_value(expression[-1], feature)
    
    result_type = get_value(expression[-1], feature)
    if isinstance(result_type, int) or isinstance(result_type, float):
        for i in range(2, len(expression), 2):
            if value < expression[i]:
                right_value = get_value(expression[i+1], feature)
                left_value = get_value(expression[i-1], feature)
                return ((value - expression[i-2]) / (expression[i] - expression[i-2])) * (right_value - left_value) + left_value
    else:
        return interpolate_color(expression, method, value, feature)
    
    # todo: implement exponentional interpolation

def get_value(expression, feature):
    if isinstance(expression, list):
        op = expression[0]
        values = expression[1:]
        
        if not isinstance(op, str):
            return expression
        
        if op == '!':
            return not get_value(values[0], feature)
        elif op == '==':
            return get_value(values[0], feature) == get_value(values[1], feature)
        elif op == '!=':
            return get_value(values[0], feature) != get_value(values[1], feature)
        elif op == '>':
            return get_value(values[0], feature) > get_value(values[1], feature)
        elif op == '<':
            return get_value(values[0], feature) < get_value(values[1], feature)
        elif op == '>=':
            return get_value(values[0], feature) >= get_value(values[1], feature)
        elif op == '<=':
            return get_value(values[0], feature) <= get_value(values[1], feature)
        elif op == '+':
            return get_value(values[0], feature) + get_value(values[1], feature)
        elif op == '-':
            return get_value(values[0], feature) - get_value(values[1], feature)
        elif op == '*':
            return get_value(values[0], feature) * get_value(values[1], feature)
        elif op == '/':
            return get_value(values[0], feature) / get_value(values[1], feature)
        elif op == 'sqrt':
            return math.sqrt(get_value(values[0], feature))
        elif op == 'zoom':
            return properties['zoom']
        elif op == 'all':
            for value in values:
                if not get_value(value, feature):
                    return False
            return True
        elif op == 'any':
            for value in values:
                if get_value(value):
                    return True
            return False
        elif op == 'at':
            if len(values) != 2:
                raise ValueError()
            if not isinstance(values[2], list):
                raise TypeError()
            return get_value(values[2][get_value(values[1], feature)], feature)
        elif op == 'get':
            if values[0] in feature['properties']:
                return feature['properties'][values[0]]
            else:
                return 0
        elif op == 'has':
            if len(values) == 1:
                return bool(values[0] in feature['properties'])
            else:
                raise ValueError()
        elif op == 'literal':
            return values[0]
        elif op == 'to-number':
            return int(get_value(values[0], feature))
        elif op == 'to-string':
            return str(get_value(values[0], feature))
        elif op == 'match':
            label = get_value(values[0], feature)
            for i in range(1, len(values) - 1):
                if isinstance(values[i], list):
                    if label in values[i]:
                        return get_value(values[i+1], feature)
                else:
                    if label == values[i]:
                        return get_value(values[i+1], feature)
            return get_value(values[-1], feature)
        elif op == 'case':
            for i in range(0, len(values) - 1, 2):
                if get_value(values[i], feature):
                    return get_value(values[i+1], feature)
            return get_value(values[-1], feature)
        elif op == 'coalesce':
            for i in range(0, len(values)):
                value = get_value(values[i], feature)
                if value:
                    return value
            return get_value(values[-1], feature)
        elif op == 'step':
            label = get_value(values[0], feature)
            for i in range(2, len(values) - 1, 2):
                if values[i] > label:
                    return get_value(values[i-1], feature)
            return get_value(values[-1], feature)
        elif op == 'interpolate':
            return interpolate(values[2:], values[0], values[1], feature)
        elif op == 'geometry-type':
            geometry_type = feature['geometry']['type']
            if geometry_type == 'MultiPolygon':
                return 'Polygon'
            elif geometry_type == 'MultiLineString':
                return 'LineString'
            else:
                return geometry_type
        else:
            raise ValueError('Unknown Expression: "{}"'.format(op))
    else:
        return expression
    
def get_color(color_style, feature = None):
    if isinstance(color_style, str):
        return color_to_hex(color_style)
    else:
        return color_to_hex(get_value(color_style, feature))

def draw_geometry(f, feature, style):
    style_str = css_style(style)

    if feature['geometry']['type'] == 'Polygon':
        for coords in feature['geometry']['coordinates']:
            point_str = ''
            
            for point in coords:
                point_str += '{},{} '.format(point[0], point[1])
            
            f.write('<polygon points="{}" style="{}" />\n'.format(point_str, style_str))
    elif feature['geometry']['type'] == 'MultiPolygon':
        f.write('<g>\n')
        for polygons in feature['geometry']['coordinates']:
            for coords in polygons:
                point_str = ''
                
                for point in coords:
                    point_str += '{},{} '.format(point[0], point[1])
                
                f.write('<polygon points="{}" style="{}" />\n'.format(point_str, style_str))
        f.write('</g>\n')
    elif feature['geometry']['type'] == 'LineString':
        point_str = ''
            
        for point in feature['geometry']['coordinates']:
            point_str += '{},{} '.format(point[0], point[1])
        
        f.write('<polyline points="{}" style="{}" />\n'.format(point_str, style_str))
    elif feature['geometry']['type'] == 'MultiLineString':
        f.write('<g>\n')
        for polylines in feature['geometry']['coordinates']:
            point_str = ''
                
            for point in polylines:
                point_str += '{},{} '.format(point[0], point[1])
            
            f.write('<polyline points="{}" style="{}" />\n'.format(point_str, style_str))
        f.write('</g>\n')

def draw_symbol(f, feature, layout, paint):
    if feature['geometry']['type'] == 'Point':
        coord = feature['geometry']['coordinates']
        icon_image = None
        
        if 'icon-image' in layout:
            icon_image = layout['icon-image']
        
        if icon_image:
            sprite = load_sprite(get_value(icon_image, feature))
            size = 1
            
            if 'icon-size' in layout:
                size = get_value(layout['icon-size'], feature)
            
            size *= 8
            x = coord[0] - (sprite['size'][0] / 2) * size
            y = coord[1] + (sprite['size'][1] / 2) * size
            
            f.write('<g transform="translate({0}, {1}) scale({2}, -{2})">'.format(x, y, size))
            f.write(sprite['image'])
            f.write('</g>\n')
        
        if 'text-field' in layout:
            text = get_value(layout['text-field'], feature)
            text_style = {'fill': '#111111', 'stroke': 'none', 'text-anchor': 'middle', 'font-size': 15, 'text-align': 'center'}
            
            if 'text-font' in layout:
                text_style['font-family'] = layout['text-font'][0]
            
            if 'text-size' in layout:
                text_style['font-size'] = get_value(layout['text-size'], feature) * 8
                text_style['stroke-width'] = text_style['font-size'] / 4
            
            if 'text-color' in paint:
                text_style['fill'] = get_color(paint['text-color'], feature)
                
            if 'text-halo-color' in paint:
                text_style['stroke'] = get_color(paint['text-halo-color'], feature)
            
            x = coord[0]
            y = coord[1]
            
            if 'text-offset' in layout:
                text_offset = get_value(layout['text-offset'], feature)
                
                x += text_offset[0] * text_style['font-size']
                y -= text_offset[1] * text_style['font-size']
            
            if text_style['stroke'] != 'none':
                f.write('<text x="0" y="0" transform="translate({}, {}) scale(1, -1)" style="{}">{}</text>\n'.format(x, y, css_style(text_style), text))
            
            text_style['stroke'] = 'none'
            f.write('<text x="0" y="0" transform="translate({}, {}) scale(1, -1)" style="{}">{}</text>\n'.format(x, y, css_style(text_style), text))

def load_sprite(sprite_id):
    if sprite_id in sprite_cache:
        return sprite_cache[sprite_id]
    
    sprite_path = resource_path('styles/{}.svg'.format(sprite_id))
    
    with open(sprite_path, mode='r', encoding='utf-8') as f:
        svg_text = f.read()
    
    match = re.match(r'<svg (.*?)>(.*)</svg>', svg_text)
    if match:
        w = re.search(r'width="([0-9]+)"', match[1])
        h = re.search(r'height="([0-9]+)"', match[1])
        
        sprite_cache[sprite_id] = {'image': match[2], 'size': (int(w[1]), int(h[1]))}
        return sprite_cache[sprite_id]
    else:
        raise ValueError()

def load_tile(style_id, token, x, y, zoom, draw_full_svg = True, clip_mask = True, fp = None):
    properties['x'] = x
    properties['y'] = y
    properties['zoom'] = zoom
    
    # Load styles
    style_response = requests.get(style_url.format(style_id), params = {'access_token': token})
    styles = style_response.json()
    
    if style_response.status_code != 200:
        if 'message' in styles:
            raise MapBoxError(styles['message'])
    
    # Get tileset sources
    if re.match(r'mapbox://', styles['sources']['composite']['url']) and styles['sources']['composite']['type'] == 'vector':
        sources = styles['sources']['composite']['url'][9:]
    else:
        raise ValueError()
    
    # Load tilesets
    tile_response = requests.get(tile_url.format(sources, zoom, x, y), params = {'access_token': token})

    tile = mapbox_vector_tile.decode(tile_response.content)
    
    if fp == None:
        f = io.StringIO()
    else:
        f = fp
        
    if draw_full_svg:
        f.write('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n')
        f.write('<svg width="4096" height="4096" viewBox="0 0 4096 4096" xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"><style></style>\n')
        f.write('<sodipodi:namedview id="namedview1" pagecolor="#ffffff" bordercolor="#cccccc" borderopacity="1" inkscape:deskcolor="#e5e5e5"/>\n')
    
    if clip_mask:
        f.write('<defs><clipPath id="map-clip-mask"><rect x="0" y="0" width="4112" height="4112" /></clipPath></defs>\n')
        f.write('<g id="map" transform="scale(1, -1) translate(0, -4096)" clip-path="url(#map-clip-mask)">')
    else:
        f.write('<g id="map" transform="scale(1, -1) translate(0, -4096)">')
    
    for layer in styles['layers']:
        if 'minzoom' in layer:
            if layer['minzoom'] > properties['zoom']:
                continue
        
        if layer['type'] == 'background':
            if 'background-color' in layer['paint']:
                fill = get_color(layer['paint']['background-color'])
                f.write('<g id="{0}"><rect x="0" y="0" width="4096" height="4096" fill="{1}" stroke="{1}" stroke-width="32" /></g>'.format(layer['id'], fill))
        else:
            if not layer['source-layer'] in tile:
                continue
            
            f.write('<g id="{}">'.format(layer['id']))
            source_layer = tile[layer['source-layer']]
            
            for feature in source_layer['features']:
                draw_filter = True
                
                if 'filter' in layer:
                    draw_filter = get_value(layer['filter'], feature)
                
                if draw_filter:
                    if layer['type'] == 'fill':
                        feature_style = {'fill': '#000000', 'opacity': 1}
                        
                        if 'paint' in layer:
                            if 'fill-color' in layer['paint']:
                                feature_style['fill'] = get_color(layer['paint']['fill-color'], feature)
                            
                            if 'opacity' in layer['paint']:
                                feature_style['opacity'] = get_value(layer['paint']['opacity'], feature)
                        
                        draw_geometry(f, feature, feature_style)
                    elif layer['type'] == 'line':
                        feature_style = {'fill': 'none', 'stroke': '#000000', 'stroke-width': 1, 'stroke-opacity': 1}
                        
                        if 'paint' in layer:
                            if 'line-color' in layer['paint']:
                                feature_style['stroke'] = get_color(layer['paint']['line-color'], feature)
                                
                            if 'line-width' in layer['paint']:
                                feature_style['stroke-width'] = get_value(layer['paint']['line-width'], feature) * 8
                            
                            if 'line-opacity' in layer['paint']:
                                feature_style['stroke-opacity'] = get_value(layer['paint']['line-opacity'], feature)
                            
                            if 'line-dasharray' in layer['paint']:
                                if not isinstance(layer['paint']['line-dasharray'], list):
                                    raise TypeError()
                                
                                dasharray_str = ''
                                for dash in layer['paint']['line-dasharray']:
                                    dasharray_str += '{} '.format(dash)
                                    
                                feature_style['stroke-dasharray'] = dasharray_str
                        
                        if 'layout' in layer:
                            if 'line-cap' in layer['layout']:
                                feature_style['stroke-linecap'] = get_value(layer['layout']['line-cap'], feature)
                                
                            if 'line-join' in layer['layout']:
                                feature_style['stroke-linejoin'] = get_value(layer['layout']['line-join'], feature)
                        
                        draw_geometry(f, feature, feature_style)
                    elif layer['type'] == 'symbol':
                        draw_symbol(f, feature, layer['layout'], layer['paint'])
            
            f.write('</g>')
    
    f.write('</g>')
        
    if draw_full_svg:
        f.write('</svg>')
    
    if fp == None:
        result = f.getvalue()
        f.close()
        return result