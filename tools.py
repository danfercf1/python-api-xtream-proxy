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