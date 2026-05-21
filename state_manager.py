import json
import logging
import os

logger = logging.getLogger('rimera-bot.state')

class StateManager:
    def __init__(self, cache_file='cache.json'):
        self.cache_file = cache_file
        self.state = self.load_state()

    def load_state(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading cache: {e}")
        return {
            "Twitter": [],
            "TikTok": [],
            "Website": [],
            "Tumblr": [],
            "Instagram": [],
            "Spotify": [],
            "YouTube": [],
        }

    def save_state(self):
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.state, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving cache: {e}")

    def get_new_items(self, source, items):
        if source not in self.state:
            self.state[source] = []

        if isinstance(self.state[source], dict):
            seen_ids = set(self.state[source].keys())
        else:
            seen_ids = set(self.state[source])
        
        new_items = []
        
        for item in items:
            item_id = str(item['id'])
            if item_id not in seen_ids:
                new_items.append(item)
                if isinstance(self.state[source], dict):
                    self.state[source][item_id] = self._snapshot_item(item)
                else:
                    self.state[source].append(item_id)
                seen_ids.add(item_id)
        
        # Keep only the last 100 IDs per source to keep cache small
        if isinstance(self.state[source], list) and len(self.state[source]) > 100:
            self.state[source] = self.state[source][-100:]
            
        if new_items:
            self.save_state()
            
        return new_items

    def get_product_updates(self, items):
        source = 'Website'
        first_run = self.is_first_run(source)
        current_state = self.state.get(source, {})
        if isinstance(current_state, list):
            current_state = {str(item_id): {} for item_id in current_state}

        updates = []

        for item in items:
            item_id = str(item['id'])
            previous = current_state.get(item_id)
            snapshot = self._snapshot_item(item)

            if previous is None:
                item['event_type'] = 'new'
                if not first_run:
                    updates.append(item)
            elif previous.get('sold_out') is True and snapshot.get('sold_out') is False:
                item['event_type'] = 'restocked'
                updates.append(item)
            elif previous.get('available') is False and snapshot.get('available') is True:
                item['event_type'] = 'restocked'
                updates.append(item)

            current_state[item_id] = snapshot

        self.state[source] = current_state
        self._trim_product_state(source)
        self.save_state()
        return updates

    def is_first_run(self, source):
        return len(self.state.get(source, [])) == 0

    @staticmethod
    def _snapshot_item(item):
        return {
            'title': item.get('title') or item.get('content', ''),
            'url': item.get('url', ''),
            'price': item.get('price', ''),
            'sold_out': bool(item.get('sold_out')),
            'available': bool(item.get('available', not item.get('sold_out'))),
        }

    def _trim_product_state(self, source, limit=250):
        if not isinstance(self.state.get(source), dict):
            return
        if len(self.state[source]) <= limit:
            return
        items = list(self.state[source].items())[-limit:]
        self.state[source] = dict(items)
