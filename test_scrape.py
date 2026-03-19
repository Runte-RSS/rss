# test_scrape.py
from generate_feed import find_latest_chapter

url = "https://manhuabuddy.com/manhwa/shut-up-evil-dragon-i-dont-want-to-raise-a-child-with-you-anymore"
result = find_latest_chapter(url)
print("RESULT:", result)
