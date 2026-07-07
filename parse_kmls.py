import os
import json
import xml.etree.ElementTree as ET

def get_kml_files(root_dir):
    kml_files = []
    for root, dirs, files in os.walk(root_dir):
        for f in files:
            if f.lower().endswith('.kml'):
                kml_files.append(os.path.join(root, f))
    return kml_files

def extract_center_from_kml(filepath):
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
        ns = {'kml': 'http://www.opengis.net/kml/2.2'}
        
        point = root.find('.//kml:Point/kml:coordinates', ns)
        if point is not None and point.text:
            coords = point.text.strip().split(',')
            return {"lng": float(coords[0]), "lat": float(coords[1])}
            
        coords_texts = []
        for tag in ['.//kml:Polygon//kml:coordinates', './/kml:LineString//kml:coordinates']:
            for c in root.findall(tag, ns):
                if c.text:
                    coords_texts.append(c.text.strip())
                    
        if coords_texts:
            lat_sum = 0
            lng_sum = 0
            count = 0
            for ct in coords_texts:
                points = ct.split()
                for p in points:
                    parts = p.split(',')
                    if len(parts) >= 2:
                        lng_sum += float(parts[0])
                        lat_sum += float(parts[1])
                        count += 1
            if count > 0:
                return {"lng": round(lng_sum/count, 4), "lat": round(lat_sum/count, 4)}
                
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
    return None

def extract_polygons_from_kml(filepath):
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
        ns = {'kml': 'http://www.opengis.net/kml/2.2'}
        polygons = []
        for tag in ['.//kml:Polygon//kml:coordinates', './/kml:LineString//kml:coordinates']:
            for c in root.findall(tag, ns):
                if c.text:
                    points = c.text.strip().split()
                    poly = []
                    for p in points:
                        parts = p.split(',')
                        if len(parts) >= 2:
                            poly.append([float(parts[1]), float(parts[0])]) # Leaflet usa [lat, lng]
                    if poly:
                        polygons.append(poly)
        return polygons
    except Exception as e:
        print(f"Error parsing polygons {filepath}: {e}")
        return []

def build_coords_map():
    kml_files = get_kml_files(r'c:\Users\ruand\Desktop\app-migrado')
    coords_map = {}
    polygons_map = {}
    
    for f in kml_files:
        basename = os.path.basename(f)
        name_without_ext = os.path.splitext(basename)[0].upper()
        
        parent_dir = os.path.basename(os.path.dirname(f)).upper()
        praca_name = parent_dir.replace("KML - ", "").replace("KML-", "").strip()
        
        key = f"{praca_name}|{name_without_ext}"
        
        center = extract_center_from_kml(f)
        if center:
            coords_map[key] = center
            
        polygons = extract_polygons_from_kml(f)
        if polygons:
            polygons_map[key] = polygons
            
    with open(r'c:\Users\ruand\Desktop\app-migrado\coordenadas_kml.json', 'w', encoding='utf-8') as out:
        json.dump(coords_map, out, indent=2, ensure_ascii=False)
        
    with open(r'c:\Users\ruand\Desktop\app-migrado\polygons_kml.js', 'w', encoding='utf-8') as out:
        out.write("const KML_POLYGONS = " + json.dumps(polygons_map, ensure_ascii=False) + ";")
        
    print(json.dumps(coords_map, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    build_coords_map()
