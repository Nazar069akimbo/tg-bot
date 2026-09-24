import requests

def search_duckduckgo(query):
    try:
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json"},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('Abstract'):
                return data['Abstract']
            if data.get('RelatedTopics'):
                for topic in data['RelatedTopics']:
                    if 'Text' in topic:
                        return topic['Text']
            return None
    except:
        return None
    return None
