import re
import zlib

class Tools:
    def remove_categories_by_name(self, categories_from_server):
        categories_to_remove = [
            'LA| GENERAL',
            'LA| MEXICO',
            'LA| COLOMBIA',
            'LA| ARGENTINA',
            'LA| COSTA RICA',
            'LA| ECUADOR',
            'LA| ECUADOR DAZN PPV',
            'LA| GUATEMALA',
            'LA| HONDURAS',
            'LA| NICARAGUA',
            'LA| PERU',
            'LA| CHILE',
            'LA| PANAMA',
            'LA| R.DOMINICANA',
            'LA| URUGUAY',
            'LA| VENEZULA',
            'VE| VENEZUELA',
            'LA| EL SALVADOR',
        ]
        return [item for item in categories_from_server if item['category_name'] not in categories_to_remove]
    
    def remove_streams_by_id(self, ids_stream_from_db, streams_from_server):
        return [item for item in streams_from_server if item['stream_id'] not in ids_stream_from_db]

    def merge_categories(self, category_from_server, category_from_db):
        merged_dict = category_from_db.copy()
        for item in category_from_server:
            # Prioritize items from dict_array2
            existing_item = next((i for i in merged_dict if i['category_name'] == item['category_name']), None)
            if existing_item:
                merged_dict.remove(existing_item)
            merged_dict.append(item)
        return merged_dict

    def parse_m3u_categories(self, m3u_text: str):
        """Extract unique categories from an M3U playlist (group-title)."""
        groups: dict[str, int] = {}
        for line in (m3u_text or "").splitlines():
            if not line.startswith("#EXTINF:"):
                continue
            m = re.search(r'group-title="([^"]*)"', line)
            if not m:
                continue
            name = (m.group(1) or "").strip()
            if not name:
                continue
            if name not in groups:
                # Stable-ish deterministic int id from name
                cid = zlib.adler32(name.encode("utf-8")) & 0x7FFFFFFF
                if cid == 0:
                    cid = 1
                groups[name] = cid

        return [
            {"category_id": cid, "category_name": name, "parent_id": 0}
            for name, cid in groups.items()
        ]

    def parse_m3u_streams(self, m3u_text: str, category_name_to_id: dict[str, int]):
        """Extract streams from an M3U playlist into a shape similar to Xtream player_api get_live_streams."""
        lines = (m3u_text or "").splitlines()
        out = []
        i = 0
        num = 1
        while i < len(lines):
            line = lines[i].strip()
            if not line.startswith("#EXTINF:"):
                i += 1
                continue
            extinf = line
            url = ""
            if i + 1 < len(lines):
                url = lines[i + 1].strip()

            # Parse fields
            name = extinf.split(",")[-1].strip() if "," in extinf else "Unknown"
            group = ""
            m = re.search(r'group-title="([^"]*)"', extinf)
            if m:
                group = (m.group(1) or "").strip()
            category_id = category_name_to_id.get(group, 0)

            tvg_logo = ""
            m = re.search(r'tvg-logo="([^"]*)"', extinf)
            if m:
                tvg_logo = (m.group(1) or "").strip()

            tvg_id = ""
            m = re.search(r'tvg-id="([^"]*)"', extinf)
            if m:
                tvg_id = (m.group(1) or "").strip()

            # Try to extract stream_id from /.../<id>.ts or .m3u8
            stream_id = None
            m = re.search(r"/(\d+)\.(?:ts|m3u8)(?:\?.*)?$", url)
            if m:
                try:
                    stream_id = int(m.group(1))
                except Exception:
                    stream_id = None
            if stream_id is None:
                stream_id = zlib.adler32(url.encode("utf-8")) & 0x7FFFFFFF
                if stream_id == 0:
                    stream_id = 1

            out.append(
                {
                    "num": num,
                    "name": name,
                    "stream_type": "live",
                    "stream_id": stream_id,
                    "stream_icon": tvg_logo,
                    "epg_channel_id": tvg_id,
                    "added": None,
                    "is_adult": 0,
                    "category_id": category_id,
                    "category_ids": None,
                    "custom_sid": None,
                    "tv_archive": 0,
                    "direct_source": url,
                    "tv_archive_duration": 0,
                }
            )
            num += 1
            i += 2
        return out