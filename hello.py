import requests

def get_binance_news():
    """获取Binance官方新闻"""
    api_url = "https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list/query"
    
    params = {
        "catalogId": "48",
        "pageNo": 1,
        "pageSize": 5
    }
    
    try:
        response = requests.get(api_url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data.get("success"):
            articles = data.get("data", {}).get("articles", [])
            print("Binance最新公告:")
            for i, article in enumerate(articles, 1):
                title = article.get("title")
                url = f"https://www.binance.com/zh-CN/support/announcement/{article.get('code')}"
                print(f"\n{i}. {title}")
                print(f"   {url}")
        else:
            print("API请求失败:", data.get("message", "未知错误"))
    except Exception as e:
        print(f"获取新闻失败: {e}")

if __name__ == "__main__":
    get_binance_news()
