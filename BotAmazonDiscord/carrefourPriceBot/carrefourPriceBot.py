import pandas as pd
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

# Classe que representa o bot para verificar preços na Carrefour
class CarrefourPriceBot():
    def __init__(self, search_query, expected_price, pages, user, loop, times):
        self.url = "https://www.carrefour.com.br"
        self.search_query = search_query
        self.priceList = []  # Lista para armazenar os preços encontrados
        self.expected_price = expected_price
        self.pages = pages  # Número de páginas a serem verificadas
        self.user = user  # Objeto para enviar notificações para o usuário
        self.loop = loop
        self.times = times
        self.url_busca = None
        self.stop_search = False  # Controle de interrupção
        self.products_info = []
        self.product_names = []

        # Configurações do navegador Chrome
        self.options = Options()
        user_agent = userAgent
        self.options.add_argument(f'user-agent={user_agent}')
        #options.add_argument('--headless')
        self.options.add_argument('--disable-gpu')
        self.options.add_argument('--window-size=1920x1080')
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--ignore-certificate-errors')
        self.options.add_experimental_option('excludeSwitches', ['enable-logging'])
        self.options.add_argument("--disable-blink-features=AutomationControlled")
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

    # Método para realizar a pesquisa do produto na Carrefour
    def search_product(self):
        search_url = f"{self.url}/busca/{self.search_query}"
        if " " in self.search_query:
            self.search_query = self.search_query.replace(" ", "-")
        self.driver.get(search_url)


    # Método para verificar os preços dos produtos nas páginas
    def check_prices(self):

        try:
            # Obtém os links dos produtos na página atual
            sleep(3)
            product_cards = self.driver.find_elements(By.CSS_SELECTOR, "div.carrefourbr-carrefour-components-0-x-galleryItem")

            print(f"\nEncontrados {len(product_cards)} produtos na página atual.\n")

            for card in product_cards:
                if self.stop_search:  # Verificar antes de cada ação
                    break

                try:
                    try:
                        link = card.find_element(By.CSS_SELECTOR, "a").get_attribute('href')
                    except Exception as e:
                        print(f"Erro ao tentar encontrar o link do produto")
                        continue
                    
                    try:
                        # Extrai o título do produto
                        title = card.find_element(By.CSS_SELECTOR, "h2.carrefourbr-carrefour-components-0-x-productName").text
                    except Exception as e:
                        print(f"Erro ao tentar encontrar o título do produto")
                        continue

                    try:
                        # Extrai o preço do produto
                        price_text = card.find_element(By.CSS_SELECTOR, "span.vtex-product-price-1-x-spotPriceValue").text
                        price = float(price_text.replace('R$', '').replace('.', '').replace(',', '.').strip())
                    except Exception as e:
                        print(f"Erro ao tentar encontrar o preço do produto")
                        continue

                    product_data = {
                        "url": link,
                        "title": title,
                        "preço": price
                    }

                    # Verifica se o produto já foi processado

                    if product_data not in self.products_info:
                        # Adiciona o produto à lista de produtos
                        self.products_info.append(product_data)
                        self.product_names.append(product_data["title"])

                        if self.expected_price == None:
                            
                            asyncio.run_coroutine_threadsafe(self.notify_discord_about_monitoring_new_product(product_data['title'], price, product_data["url"]), self.loop)
                            
                            print(f"Novo produto!\nPreço encontrado para '{product_data['title']}' \nPreço: R${price}\n\n")

                        elif price <= self.expected_price:

                            asyncio.run_coroutine_threadsafe(self.notify_discord_about_new_product(product_data['title'], price, product_data["url"]), self.loop)

                            print(f"Novo produto!\nPreço encontrado para '{product_data['title']}' \nPreço: R${price}\n\n")                        
                    
                    else:
                        # Verifica se o preço do produto mudou
                        for product in self.products_info:

                            if product["title"] == product_data["title"]:

                                if product["preço"] != product_data["preço"]:

                                    product["preço"] = product_data["preço"]

                                    if self.expected_price == None:
                                        
                                        asyncio.run_coroutine_threadsafe(self.notify_discord_about_monitoring_new_price(product['title'], price, product["url"]), self.loop)
                                        
                                        print(f"Preço mudou para '{product['title']}' \nPreço: R${price}\n\n")

                                    elif price <= self.expected_price:

                                        asyncio.run_coroutine_threadsafe(self.notify_discord_about_change_in_price(product['title'], price, product["url"]), self.loop)

                                        print(f"Preço mudou para '{product['title']}' \nPreço: R${price}\n\n")                                    

                except NoSuchElementException:
                    print(f"Não foi possível encontrar o título ou preço para a URL: {product_data['url']}")
                    continue
                except ValueError:
                    print(f"Formato de preço inválido para '{product_data['title']}'")
                    continue
                except TimeoutException:
                    print(f"O tempo de espera excedeu enquanto procurava pelo título ou preço de '{product_data['title']}'")
                    continue

        except Exception as e:
            print(f"Ocorreu um erro geral ao tentar buscar os produtos e preços: {e}")

        # Armazena e retorna a lista de produtos e preços
        print(self.products_info)
        return self.products_info
    
     # Método para navegar para a próxima página de resultados   
    def next_page(self):
        try:
            self.driver.execute_script("window.scrollBy(0, 1000)")
            sleep(1)
            button = self.driver.find_element(By.CSS_SELECTOR, '.carrefourbr-carrefour-components-0-x-Pagination_NextButtonContainer a')
            self.driver.get(button.get_attribute('href'))
            return True
        except Exception as e:
            print("Botão de próxima página não encontrado.")
            return False
            
    def stop_searching(self):
        self.stop_search = True

    # Método para realizar a busca de preços de forma síncrona
    def search_prices_sync(self):
        print(f"Monitorando a busca por '{self.search_query}' no Carrefour")    
        if self.times == "indeterminado":
            while not self.stop_search:
                self.restart_driver()
                self.search_product()
                sleep(1)
                self.driver.fullscreen_window()
                for _ in range(self.pages):
                    print(f"Monitorando página {_ + 1} de {self.pages}")
                    if self.stop_search:
                        break
                    self.check_prices()
                    sleep(1)  
                    if not self.next_page():
                        break
                    sleep(1)
        else:
            for _ in range(self.times):
                if self.stop_search:
                    break
                self.restart_driver()
                self.driver.get(self.url)
                sleep(0.7)
                self.search_product()
                sleep(1)

                for _ in range(self.pages):
                    print(f"Monitorando página {_ + 1} de {self.pages}")
                    if self.stop_search:
                        break
                    self.check_prices()
                    sleep(1)
                    if not self.next_page():
                        break
                    sleep(1)
        
        self.driver.quit()

    
    # Método para realizar a busca de preços de forma síncrona
    def check_link_prices(self, link):
        print(f"Monitorando link: {link}")
        if self.times == "indeterminado":
            while not self.stop_search:
                self.restart_driver()
                self.driver.get(link)
                self.driver.fullscreen_window()
                self.driver.execute_script("window.scrollTo(0, 700)")
                sleep(0.7)
                search_url = self.driver.current_url

                for _ in range(self.pages):
                    print(f"Monitorando página {_ + 1} de {self.pages}")
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
                print(f"Monitorando página {_ + 1} de {self.pages}")
                if self.stop_search:
                    break
                self.restart_driver()
                self.driver.get(link)
                self.driver.fullscreen_window()
                self.driver.execute_script("window.scrollTo(0, 700)")
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
                sleep(3)
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
                title_element = self.driver.find_element(By.CLASS_NAME, "vtex-store-components-3-x-productBrand")
                title = title_element.text

                # Tenta localizar o preço do produto
                try:
                    price_element = self.driver.find_elements(By.CLASS_NAME, "carrefourbr-carrefour-components-0-x-sellingPriceValue")[1]
                except IndexError:
                    price_element = self.driver.find_element(By.CLASS_NAME, "carrefourbr-carrefour-components-0-x-sellingPriceValue")

                price_text = price_element.text.replace('R$', '').replace('.', '').replace(',', '.').strip()

                price = float(price_text)

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

