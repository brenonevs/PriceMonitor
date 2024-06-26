import pandas as pd
import threading
import asyncio
import os

from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from time import sleep, time

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Obtém o valor da variável de ambiente "USER_AGENT"
userAgent = os.getenv("USER_AGENT")

# Classe que representa o bot para verificar preços na MagineLuiza
class MagazineLuizaPriceBot():
    def __init__(self, search_query, expected_price, pages, user, loop, times):
        self.url = "https://www.magazineluiza.com.br/"
        self.search_query = search_query
        self.priceList = []  # Lista para armazenar os preços encontrados
        self.expected_price = expected_price
        self.pages = pages  # Número de páginas a serem verificadas
        self.user = user  # Objeto para enviar notificações para o usuário
        self.loop = loop
        self.times = times
        self.stop_search = False  # Controle de interrupção
        self.processed_links = set()  # Conjunto para armazenar URLs já processados neste ciclo
        self.products_info = []
        self.product_names = []  

        # Configurações do navegador Chrome
        self.options = Options() 
        self.user_agent = userAgent
        self.options.add_argument(f'user-agent={self.user_agent}')
        #self.options.add_argument('--headless')
        self.options.add_argument('--disable-gpu')
        self.options.add_argument('--window-size=1920x1080')
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--ignore-certificate-errors')
        self.options.add_experimental_option('excludeSwitches', ['enable-logging'])
        self.options.add_argument('--disable-blink-features=AutomationControlled')
        self.options.add_argument('--disable-extensions')
        self.options.add_argument('--disable-images')

        service = Service(ChromeDriverManager().install())
        service.log_path = 'NUL'

        self.driver = webdriver.Chrome(service=service, options=self.options)

    async def notify_discord_about_new_product(self, title, price, url):
        message = "-" * 70 + f"\n\n**Novo Produto!**\n**Produto:** {title}\n**Preço Abaixo do Esperado:** ${price}\n**Link:** {url}\n\n" + "-" * 70
        await self.user.send(message)

    async def notify_discord_about_change_in_price(self, title, price, url):
        message = "-" * 70 + f"\n\n**Mudança no preço**\n**Produto:** {title}\n**Preço Abaixo do Esperado:** ${price}\n**Link:** {url}\n\n" + "-" * 70
        await self.user.send(message)


    async def notify_discord_about_monitoring_new_product(self, title, price, url):
        message = "-" * 70 + f"\n\n**Novo Produto!**\n**Produto:** {title}\n**Preço Monitorado:** ${price}\n**Link:** {url}\n\n" + "-" * 70
        await self.user.send(message)

    async def notify_discord_about_monitoring_new_price(self, title, price, url):
        message = "-" * 70 + f"\n\n**Mudança no preço!**\n**Produto:** {title}\n**Preço Monitorado:** ${price}\n**Link:** {url}\n\n" + "-" * 70
        await self.user.send(message)

    async def notify_discord_about_error(self):
        message = "-" * 70 + f"\n\nOcorreu um erro ao monitorar o produto. \n\nO produto pode estar sem estoque, a página pode estar indisponível ou a estrutura do site mudou!\n\n" + "-" * 70
        await self.user.send(message)

    # Método para realizar a pesquisa do produto na Magazine
    def search_product(self):
        search_input = self.driver.find_element(By.ID, 'input-search')
        search_input.send_keys(self.search_query)
        search_input.submit()
        sleep(5)

    # Método para verificar os preços dos produtos nas páginas
    def check_prices(self):
        product_links = []

        try:
            # Obtém os links dos produtos na página atual
            product_cards = self.driver.find_elements(By.CSS_SELECTOR, "li.sc-kTbCBX.ciMFyT a")
            for card in product_cards:
                product_links.append({
                    "url": card.get_attribute('href')
                })

            print(f"Encontrados {len(product_links)} produtos na página atual.")

            for product in product_links:
                if self.stop_search:
                    break
                self.driver.get(product["url"])
                self.driver.fullscreen_window()
                sleep(1)

                try:
                    # Espera até que o título do produto esteja visível
                    title_element = WebDriverWait(self.driver, 10).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, "h1[data-testid='heading-product-title']"))
                    )
                    product["title"] = title_element.text

                    # Tenta encontrar o preço do produto com o primeiro seletor
                    try:
                        price_element = WebDriverWait(self.driver, 5).until(
                            EC.visibility_of_element_located((By.XPATH, '//*[@id="__next"]/div/main/section[5]/div[5]/div/div/div/div'))
                        )
                    except Exception:
                        # Se o preço não for encontrado, tenta com o segundo seletor
                        try:
                            price_element = WebDriverWait(self.driver, 5).until(
                                EC.visibility_of_element_located((By.XPATH, '//*[@id="__next"]/div/main/section[5]/div[5]/div/div/div/div/p'))
                            )
                        except Exception:
                            price_element = WebDriverWait(self.driver, 5).until(
                                EC.visibility_of_element_located((By.XPATH, '//*[@id="__next"]/div/main/section[5]/div[4]/div/div/div/div'))
                            )

                    price_text = price_element.text.replace('R$', '').replace('.', '').replace(',', '.').replace("\nno Pix", "").strip()
                    price = float(price_text)

                    product["preço"] = price

                    product_data = {
                        "title": product["title"],
                        "preço": product["preço"],
                        "url": product["url"]
                    }

                    if product_data['title'] not in self.product_names:
                        # Adiciona o produto à lista de produtos
                        self.products_info.append(product_data)
                        self.product_names.append(product_data['title'])

                        if self.expected_price == None:
                            asyncio.run_coroutine_threadsafe(self.notify_discord_about_monitoring_new_product(product['title'], price, product["url"]), self.loop)
                            print(f"Novo produto!\nPreço encontrado para '{product['title']}' \nPreço: R${price}\n\n")

                        elif price <= self.expected_price:
                            asyncio.run_coroutine_threadsafe(self.notify_discord_about_new_product(product['title'], price, product["url"]), self.loop)
                            print(f"Novo produto!\nPreço encontrado para '{product['title']}' \nPreço: R${price}\n\n")                              
                    else:
                        for product_info in self.products_info:
                            if product_info["title"] == product_data["title"] and product_info["preço"] != product_data["preço"]:
                                product_info["preço"] = product_data["preço"]

                                if self.expected_price == None:
                                    asyncio.run_coroutine_threadsafe(self.notify_discord_about_monitoring_new_price(product['title'], price, product["url"]), self.loop)
                                    print(f"Preço mudou para '{product['title']}' \nPreço: R${price}\n\n")

                                elif price <= self.expected_price:
                                    asyncio.run_coroutine_threadsafe(self.notify_discord_about_change_in_price(product['title'], price, product["url"]), self.loop)
                                    print(f"Preço mudou para '{product['title']}' \nPreço: R${price}\n\n")                               

                except NoSuchElementException:
                    print(f"\n\nNão foi possível encontrar o título ou preço para a URL: {product['url']}\n\n")
                except ValueError:
                    print(f"\n\nFormato de preço inválido para '{product['title']}'\n\n")
                except TimeoutException:
                    print(f"\n\nO tempo de espera excedeu enquanto procurava pelo título ou preço de '{product['title']}'\n\n")

        except Exception as e:
            print(f"Ocorreu um erro geral ao tentar buscar os produtos e preços: {e}")

        self.priceList = product_links
        print(self.priceList)
        return self.priceList

    def next_page(self):
        self.current_page += 1  # Incrementa o número da página
        if self.current_page > self.pages:
            print("Alcançou o limite de páginas para verificação.")
            return False
        try:
            next_page_url = f"{self.url}busca/{self.search_query}/?page={self.current_page}"
            print(f"Navegando para a página {self.current_page}: {next_page_url}")
            self.driver.get(next_page_url)
            sleep(1)  
            return True
        except Exception as e:
            print(f"Ocorreu um erro ao tentar ir para a próxima página: {e}")
            return False
        
    def stop_searching(self):
        self.stop_search = True

    # Método para realizar a busca de preços de forma síncrona
    def search_prices_sync(self):
        if self.times == "indeterminado":
            while not self.stop_search:
                self.current_page = 1
                self.restart_driver()
                self.driver.get(self.url)
                sleep(0.7)
                self.search_product()
                sleep(1)
                search_url = self.driver.current_url

                for _ in range(self.pages):
                    if self.stop_search:
                        break
                    self.check_prices()
                    self.driver.get(search_url)
                    sleep(1)
                    if not self.next_page():
                        break
                    search_url = self.driver.current_url
                    sleep(1)
        else:
            for _ in range(self.times):
                self.current_page = 1
                if self.stop_search:
                    break
                self.restart_driver()
                self.driver.get(self.url)
                sleep(0.7)
                self.search_product()
                sleep(1)
                search_url = self.driver.current_url

                for _ in range(self.pages):
                    if self.stop_search:
                        break
                    self.check_prices()
                    self.driver.get(search_url)
                    sleep(1)
                    if not self.next_page():
                        break
                    search_url = self.driver.current_url    
                    sleep(1)
        
        self.driver.quit()

    
    # Método para realizar a busca de preços de forma síncrona
    def check_link_prices(self, link): 
        if self.times == "indeterminado":
            while not self.stop_search:
                self.current_page = 1
                self.restart_driver()
                self.driver.get(link)
                sleep(0.7)
                search_url = self.driver.current_url

                for _ in range(self.pages):
                    if self.stop_search:
                        break
                    self.check_prices()
                    sleep(1)
                    self.driver.get(search_url)
                    if not self.next_page():
                        break
                    search_url = self.driver.current_url
                    sleep(1)
        else:
            for _ in range(self.times):
                self.current_page = 1
                if self.stop_search:
                    break
                self.restart_driver()
                self.driver.get(link)
                sleep(0.7)
                self.search_product()
                sleep(1)
                search_url = self.driver.current_url

                for _ in range(self.pages):
                    if self.stop_search:
                        break
                    self.check_prices()
                    sleep(1)
                    self.driver.get(search_url) 
                    if not self.next_page():
                        break
                    search_url = self.driver.current_url
                    sleep(1)
        
        self.driver.quit()

    def restart_driver(self):
        self.driver.quit()
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=self.options)

    # Função para monitorar um link de um produto específico e se o preço dele mudou   
    def check_specific_product(self, link, expected_price):
        last_price = None  # Variável para armazenar o último preço verificado

        notified_for_price_drop = False 

        expected_price = float(expected_price)

        first_notification = True

        in_stock = True

        while not self.stop_search:
            try:
                # Tente carregar a página
                self.restart_driver()
                self.driver.get(link)
                sleep(1)
            except TimeoutException:
                # Se ocorrer um timeout, recarregue a página e vá para a próxima iteração
                print(f"Timeout ao carregar {link}, tentando recarregar.")
                try:
                    self.driver.refresh()
                except Exception as e:
                    print(f"Erro ao tentar recarregar a página: {e}")
                    continue  # Pula para a próxima iteração do loop
                continue

            try:
                # Tenta localizar o título do produto
                title_element = self.driver.find_element(By.CSS_SELECTOR, "h1.sc-fdfabab6-6.jNQQeD")
                title = title_element.text

                # Tenta localizar o preço do produto
                price_element = self.driver.find_element(By.CSS_SELECTOR, "h4.sc-5492faee-2.ipHrwP.finalPrice")
                price_text = price_element.text.replace('R$', '').replace('.', '').replace(',', '.').strip()

                price = float(price_text)

                print(f"Preço encontrado para '{title}' \nPreço: R${price}\n\n")

                if last_price is None:
                    last_price = price

                if first_notification:
                    asyncio.run_coroutine_threadsafe(self.notify_discord_about_monitoring_new_product(title, price, link), self.loop)
                    first_notification = False

                # Condição modificada para enviar notificação apenas quando o preço diminuir ou for menor que o esperado
                if price < last_price or (price < expected_price and not notified_for_price_drop):
                    asyncio.run_coroutine_threadsafe(self.notify_discord_about_monitoring_new_price(title, price, link), self.loop)
                    print(f"Preço encontrado para '{title}' \nPreço: R${price}\n\n")
                    last_price = price  # Atualiza o último preço verificado
                    notified_for_price_drop = True
                
                in_stock = True

            except NoSuchElementException:
                print(f"Não foi possível encontrar o título ou preço para a URL: {link}")
                if in_stock:
                    asyncio.run_coroutine_threadsafe(self.notify_discord_about_error(), self.loop)
                    in_stock = False    
                continue

            except WebDriverException as e:
                if "Out of Memory" in str(e):
                    print("Detectado erro 'Out of Memory'. Reiniciando o driver...")
                    self.restart_driver()


    async def search_specific_product(self, link, expected_price):
        await asyncio.get_event_loop().run_in_executor(None, self.check_specific_product, link, expected_price)

    async def search_prices(self):
        await asyncio.get_event_loop().run_in_executor(None, self.search_prices_sync)

    async def search_link_prices(self, link):
        await asyncio.get_event_loop().run_in_executor(None, self.check_link_prices, link)

    # Método para salvar os dados em um arquivo CSV
    def data_to_csv(self):
        df = pd.DataFrame(self.priceList)
        df = df.dropna(how='all')
        df.to_csv(f"{self.search_query}.csv", index=False)


