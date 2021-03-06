from urllib import parse
import re
import os
from bs4 import BeautifulSoup as bs
import optparse


import parsers.static as static 

USE_CACHE = False
AUTO_OPEN_EDITOR = False
USE_DYNAMIC_TITLE = False
ASIN_LIST_FILENAME = "asin.txt"
UPC_FILENAME = "UPC.txt"
AMAZON_URL_ROOT = "https://www.amazon.com/gp"
AMAZON_PRODUCT_URL = AMAZON_URL_ROOT+"/product/"
AMAZON_PRODUCT_LIST_URL = AMAZON_URL_ROOT+"/offer-listing/"

info_struct = {}

def process_asin(asin):
    global info_struct
    static.info("Processing Amazon product " + asin)
    try:
        html = static.save_product_page(AMAZON_PRODUCT_URL, asin, USE_CACHE)
        if html != None:
            static.info("Getting product information")
            done = parse_url_for_info(html,asin)
            if not done:
                static.error("There was an exception raised. Exiting")
                return False
             
            if AUTO_OPEN_EDITOR:
                static.open_editor(os.path.join(os.getcwd(),asin,static.TEMP_TXT))
            else:
                input("The info file has been created in %s . Press any key to continue with image download, once you're done editing the data" % asin+"/"+ static.TEMP_TXT)
             
            static.info("Getting images from HTML")
            images = parse_url_for_images(html)
            if images == None:
                static.error("Something went wrong for asin " + asin)
                return False
             
            static.info("Parsing keyword data from file")
            keywords,keywords_nomixed = static.parse_keywords(asin+"/"+ static.TEMP_TXT)
            if keywords == None or keywords_nomixed == None:
                raise Exception("No keywords provided")
 
            info_struct = static.update_and_copy_info(asin, keywords = keywords_nomixed, dyn_title = USE_DYNAMIC_TITLE)        
            static.get_images(asin, images, keywords)           
            static.modify_html_template(asin, info_struct, keywords_nomixed["LongTailKeyword"])
            return True
        else:
            static.warn("Skipping processing")
            return True
    except Exception as e:
        static.print_exception("Exception while processing asin "+ asin)
        return False
 
def run():
    static.info("Starting AZParser.")
    asin_list = static.parse_product_file(ASIN_LIST_FILENAME)
    for asin in asin_list:
        process_asin(asin.strip())
    input("Parser has finished")
    static.success("Goodbye!")
         
############################################# PRODUCT DETAILS ##################################################
 
 
def parse_url_for_info(html, asin = "."):
    global info_struct
    try:
        info_struct['bullets'] = find_bullets(html)
        info_struct['descr'] = find_description(html)
        info_struct['product'] = find_product_name(html)
        info_struct['brand'] = find_brand(html)
        info_struct['details'] = find_details(html)
        info_struct['tech_details'] = find_tech_details(html)
        info_struct['price'] = find_price(html, asin)
        info_struct['UPC'] = static.find_upc_from_file(asin, UPC_FILENAME)
        static.write_to_file(asin+"/"+static.TEMP_TXT, info_struct)                      
        return True
    except Exception as e:
        static.print_exception()
        return False
         
      
         
def find_details(html):
    static.info("Finding product details")
    res = []
    try:
        detail_html = html.find(id="prodDetails")
        if detail_html == None:
            detail_html = html.find(id="detail-bullets")
            if detail_html == None:
                static.warn("No details found")
                return None
            for li in detail_html.ul.find_all("li"):
                if li.script or li.a or li.style:
                    continue
#                 txt = li.text.split(":") 
                res.append(li.text.strip().replace("\n",""))
        else:
            for tr in detail_html.table.find_all("tr"):
                th = tr.th.getText().strip()
                if th.replace(" ","").lower() == "customerreviews":
                    res.append(th + ":" + tr.td.br.getText().strip().replace("\n",""))
#                     res[th] = tr.td.br.getText().strip()
                else:
                    res.append(th + ":"+ tr.td.getText().strip().replace("\n",""))
#                     res[th] = tr.td.getText().strip()
                 
             
    except Exception as e:
        static.print_exception()
    res.sort()
    return res
         
def find_tech_details(html):
    static.info("Finding product technical details")
    res = [] 
    try:
        detail_html = html.find(id="technicalSpecifications_feature_div")
        if detail_html == None:
            static.warn("No details found")
            return None
        for table in detail_html.find_all("table"):
            for row in table.find_all("tr"):
                res.append(row.th.getText().strip() +" : "+ row.td.getText().strip())            
    except Exception as e:
        static.print_exception()
    res.sort()
    return res
 
             
def find_product_name(html):
    static.info("Finding product name")
    try:
        return html.find(id="productTitle").getText().strip()
    except Exception as e:
        static.print_exception("Exception while trying to get product name")
        return None
             
def find_brand(html):
    static.info("Finding brand")
    try:
        brand = html.find(id="brand")
        brand_txt = brand.getText().strip()
        if brand_txt:
            return brand_txt
        else:
            static.warn("Cannot find brand name")
            if brand.name == "a":
                static.info("Will extract brand name from brand page")
                href = AMAZON_URL_ROOT+brand.get("href").replace("/","",1)
                brand_html = static.open_aux_page(href)
                meta = brand_html.find("meta", {"name": "keywords"})
                if meta: 
                    return meta.get("content")
    except Exception as e:
        static.print_exception("Exception while trying to get product brand ")
        
        return None
             
def find_bullets(html):
    static.info("Finding feature bullets")
    bullets_id = "feature-bullets"
    if html.find(id=bullets_id) == None:
        bullets_id = bullets_id+"-btf"
        if html.find(id=bullets_id)  == None:
            static.warn("No bullets were found")
            return None
    try:
        bullets = [bullet.getText().strip() for bullet in html.find(id=bullets_id).find_all("li") if (
     (
      bullet.attrs == {} or 
      not bullet.has_attr("id") or 
      "replacementPartsFitmentBullet" not in bullet.attrs['id']
     ) and
     "prime members get unlimited access to prime movies" not in bullet.getText().strip().lower() 
     )
                   ]
        return bullets
    except Exception as e:
        static.print_exception("Exception while trying to parse feature bullets ")
        return None
 
def find_description(html):
    static.info("Checking for product description")
    prod__iframe = [framescript.getText() for framescript in html.find_all("script") if re.search(r"var iframeContent",framescript.getText())]
    product_html = None
    if len(prod__iframe) == 0:
        static.warn("Product Description iFrame was not found!")
        static.info("Looking for div id='productDescription'")
        descr = html.find(id="productDescription")
        if descr:
            static.success("Found it")
            p = descr.p
            return p.getText().strip()
        return None
    else:
        obj = re.search(r"var iframeContent\s*=\s(.*?);",prod__iframe[0])
        if obj:
            try:
                product_html = bs(parse.unquote(obj.group(1)), "html.parser")
                return product_html.find(class_="productDescriptionWrapper").getText().replace("\n", "").strip()
            except Exception as e:
                static.print_exception("Exception when trying to parse product description ")
                return None
        else:
            return None
     
def find_price(html, asin):
    static.info("Finding item price")
    try:
        
        price = lookup_price_listing(asin)
        if price == None:
            static.warn("No price for this product was found. Maybe it's out of stock?")
            return 0.0
        else:
            return round(price + price*0.17,2)
    except Exception as e:
        static.print_exception("Could not parse price listing")
            
#     price_div = None
#     for tag in ["priceblock_ourprice","priceblock_dealprice", "snsPrice"]:
#         price_div = html.find(id=tag)
#         if price_div:
#             try:
#                 if tag == "snsPrice":
#                     span = [ span for span in price_div.find_all("span") if span.has_attr("class") and "a-color-price" in span["class"] and "snsPricePerUnit" not in span["class"]]
#                     price = float(span[0].getText().strip().replace("\n","").replace("$",""))
#                     return round(price + price*0.17,2)
#                 else:             
#                     price = float(price_div.getText().strip().replace("\n","").replace("$",""))
#                     return round(price + price*0.17,2)
#             except Exception as e:
#                 static.print_exception("Exception when trying to parse price ")
#                 return None   
#     if not price_div:
#         static.warn("Could not find price div")
#         # try to search for the price offering list and get first the PRIME new offer's price 
#         try:
#             price = lookup_price_listing(asin)
#             if price == None:
#                 static.warn("No price for this product was found. Maybe it's out of stock?")
#                 return 0.0
#             else:
#                 return round(price + price*0.17,2)
#         except Exception as e:
#             static.print_exception("Exception when parsing price listing for product %s"% asin)
#             return None
             
#     try:
#         span = price_div.find("span", id=tag_id)
#         if span:
#             price = float(tr.find_all("td")[1].span.getText().strip().replace("\n","").replace("$",""))
#             return round(price + price*0.17,2)
#         else:
#             print("Cannot find price")
#             return None
#     except Exception as 
#         static.p    oforolprint_exception("Exception when trying to parse price ")
#         return None   
 
 
def lookup_price_listing(asin):
    static.info("Will look up price listing for this product")
    price_listing_html = static.open_aux_page(AMAZON_PRODUCT_LIST_URL+asin)
    main_div = price_listing_html.find("div", id="olpOfferList")
    if main_div:
        prime_offers = [o for o in main_div.find_all("div", class_= "olpOffer") if o.find("span", class_= "supersaver") and o.find(class_="olpConditionColumn") and o.find(class_="olpConditionColumn").getText().strip().lower() == "new"]    
        if prime_offers:
            obj = re.search(r"\d+\.*\d*", prime_offers[0].find("div", class_="olpPriceColumn").getText().replace("\n", ""))
            if obj:
                return float(obj.group().strip())
            else:
                raise Exception("could not parse price")
    else:
        raise Exception("div#olpOfferList missing")
 
def parse_url_for_images(html):
    #data = None
    #with open("test1.txt","r", encoding="UTF-8") as f:
    #    data = f.read().replace("\n","")
    static.info("Searching for Javascript segment that has image urls")  
    obj = None
    for script in html.find_all("script"):
        obj = re.search(r"P.when\(\'A\'\).register\(\"ImageBlockATF.*?colorImages.*?initial[\'\"]*?.*?(\[\{.*?\]\}).*?colorToAsin",script.getText().replace("\n",""))
        if obj != None:
            break
    if obj == None:
        static.error("Something went wrong. No such segment exists")
        return
    data = obj.group()
    obj = re.search(r"(\[\{.*\]\})",data)
    if obj == None:
        static.error("Something went wrong. No such segment exists")
        return 
    static.success("Found segment")
    i = re.sub(r"[\[\]\{\}]", "", obj.group(1))
    static.info("Splitting")
    lst  = [re.sub(r"[\'\"]","", item) for item in i.split("\",\"")]
    #if len(lst) == 0:
    #    print("something went wrong")
    images = {}
    static.info("Gathering images by type")
    for item in lst:
        item = item.replace("\"","").replace("'","")
        #print(item)
        obj = re.search(r"(.*)\:(http.*)", item)
        if obj != None:
            #print("For type " + obj.group(1) + " URL is " + obj.group(2))
    
            try:
                images[obj.group(1)] += [obj.group(2)]
            except KeyError:
                images[obj.group(1)] = [obj.group(2)]
    static.success("Done")
    return images
         
def main():
    global USE_CACHE
    global AUTO_OPEN_EDITOR
    global USE_DYNAMIC_TITLE
    parser = optparse.OptionParser('usage%prog [--cache] [--auto-open-editor]')
    parser.add_option('-c', '--cache', dest='do_cache', action="store_true", help='cache html files')
    parser.add_option('-d', '--dyn-title', dest='dyn_title', action="store_true", help='generate title dynamically using user keywords')
    parser.add_option('-a', '--auto-open-editor', action="store_true", dest='auto_edit',help='automatically open editor')
    (options, args) = parser.parse_args()
    do_cache= options.do_cache
    auto_edit = options.auto_edit
    dyn_title = options.dyn_title
    if do_cache:
        USE_CACHE = True
        static.info("CACHE flag is set")
    if auto_edit:
        AUTO_OPEN_EDITOR = True
        static.info("AUTO_OPEN flag is set")
    if dyn_title:
        USE_DYNAMIC_TITLE = True
        static.info("USE_DYNAMIC_TITLE flag is set")
    static.info("Starting with CACHE %s and AUTO_OPEN %s and USE_DYNAMIC_TITLE %s" % ( USE_CACHE, AUTO_OPEN_EDITOR, USE_DYNAMIC_TITLE))
    #test_threading()
    run()
     
if __name__ == '__main__':
    main()
     

        