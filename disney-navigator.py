import math
import re

import folium
import networkx as nx
import osmnx as ox
import streamlit as st
from streamlit_folium import st_folium
from streamlit_js_eval import streamlit_js_eval

st.set_page_config(page_title="TDR Path Finder", layout="wide")
st.title("ディズニー専用 最短ルートナビ")

@st.cache_resource
def get_park_data(park_type):
    place = "Tokyo Disneyland" if park_type == "ランド" else "Tokyo DisneySea"
    place += ", Urayasu, Chiba, Japan"
    
    # 経路の精度を上げるため、simplify=Falseで道の曲がり角ノードをすべて保持する
    graph = ox.graph_from_place(
        place, 
        network_type='walk', 
        simplify=False, 
        retain_all=True
    )
    graph = ox.truncate.largest_component(graph, strongly=True)
    
    # アトラクション情報の取得
    tags = {'tourism': 'attraction', 'attraction': True}
    features = ox.features_from_place(place, tags)
    
    attractions = {}
    jp_pattern = re.compile(r'[ぁ-んァ-ン一-龠]')
    
    for _, row in features.iterrows():
        name = row.get('name')
        if isinstance(name, str) and jp_pattern.search(name):
            point = row.geometry.centroid
            # 建物の中を斜めに突っ切るのを防ぐため、最寄りの歩道ノードを目的地として保存
            nearest_node = ox.distance.nearest_nodes(graph, X=point.x, Y=point.y)
            attractions[name] = nearest_node
            
    return graph, attractions

# 状態管理（再描画時のデータ消失防止）
if 'route_data' not in st.session_state:
    st.session_state.route_data = None
if 'last_park' not in st.session_state:
    st.session_state.last_park = None

park_choice = st.radio("今どちらのパークにいますか？", ["ランド", "シー"], horizontal=True)

# パーク切り替え時にルートをリセットする
if st.session_state.last_park != park_choice:
    st.session_state.route_data = None
    st.session_state.last_park = park_choice

with st.spinner(f"{park_choice}のデータを読み込み中..."):
    G, spot_list = get_park_data(park_choice)

st.subheader("📍 現在地を取得")
loc = streamlit_js_eval(
    js_expressions="target.navigator.geolocation.getCurrentPosition(pos => {return {lat: pos.coords.latitude, lon: pos.coords.longitude}})", 
    key="get_location"
)

if loc:
    st.info(f"現在地を取得しました (緯度: {loc['lat']}, 経度: {loc['lon']})")

st.divider()

col1, col2 = st.columns(2)
with col1:
    options = sorted(spot_list.keys()) if spot_list else ["施設データなし"]
    start_node_name = st.selectbox("出発地（アトラクションから選ぶ）", options, key=f"start_{park_choice}")
with col2:
    end_node_name = st.selectbox("目的地", options, key=f"end_{park_choice}")

# 経路計算
if st.button("最短ルートを表示する", type="primary"):
    if not spot_list:
        st.error("施設データが読み込めませんでした。")
    else:
        dest_node = spot_list[end_node_name]
        
        # GPSデータがあれば現在地を優先、なければ選択肢の出発地を使用
        if loc:
            orig_node = ox.distance.nearest_nodes(G, X=loc['lon'], Y=loc['lat'])
        else:
            orig_node = spot_list[start_node_name]
        
        try:
            route = nx.shortest_path(G, orig_node, dest_node, weight='length')
            distance = nx.shortest_path_length(G, orig_node, dest_node, weight='length')
            
            # 徒歩時間（不動産基準の分速80mで計算し切り上げ）
            walk_time = math.ceil(distance / 80)
            route_coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]
            
            st.session_state.route_data = {
                'route_coords': route_coords,
                'distance': int(distance),
                'walk_time': walk_time
            }
        except Exception:
            st.error("経路が見つかりませんでした。")

# 地図描画
if st.session_state.route_data:
    data = st.session_state.route_data
    st.success(f"目的地まで 約 {data['distance']} メートル （徒歩 約 {data['walk_time']} 分）です！")
    
    m = folium.Map(location=data['route_coords'][0], zoom_start=17)
    folium.PolyLine(data['route_coords'], color="red", weight=6, opacity=0.8).add_to(m)
    
    # マーカー
    folium.Marker(data['route_coords'][0], popup="出発", icon=folium.Icon(color='blue')).add_to(m)
    folium.Marker(data['route_coords'][-1], popup="目的地", icon=folium.Icon(color='red')).add_to(m)
    
    # returned_objects=[] で再描画のループを防ぎ軽量化

    st_folium(m, width=1000, height=600, key=f"map_{park_choice}", returned_objects=[], use_container_width=True)
