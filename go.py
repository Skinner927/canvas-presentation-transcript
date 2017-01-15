#execfile('go.py')
import requests
from bs4 import BeautifulSoup
from bs4 import SoupStrainer
import getpass
import os.path
import pickle
import codecs
import sys
import time

# Basic Config
canvasUrl = 'https://usflearn.instructure.com/'
cookieJar = 'cookies.txt'

# Functions

def newBS(content, parser='html.parser'):
  return BeautifulSoup(content, parser)

# Gets a new requests session
def getSession():
  s = requests.Session()
  s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 6.3; WOW64; rv:31.0) Gecko/20100101 Firefox/32.0'})
  
  #restore cookies
  if os.path.isfile(cookieJar):
    with open(cookieJar) as cj:
      cookies = requests.utils.cookiejar_from_dict(pickle.load(cj))
      s.cookies = cookies
  
  return s

# Tests to see if we're logged in
# s = session
# returns True if we are, result object
def verifyLogin(s):
  r = s.get(canvasUrl);
  
  result = None
  if r.url.find('webauth.usf.edu') >= 0:
    result = False
  else:
    result = True
  
  return result, r
  
# Logs into canvas
# s = session
# Returns True on success and False on failure
def login(s):
  loggedIn, r = verifyLogin(s)
  
  if loggedIn == True:
    return True
  
  # Now we need to find the webauth form and submit our creds
  soup = newBS(r.content)
  
  # Grab the login form and all the inputs
  webAuth = soup.find('form', id='fm1')
  inputs = webAuth.find_all('input')
  
  # Collect form data
  data = {}
  for input in inputs:
    # The submit button won't have a name
    if 'name' not in input.attrs:
      if input.attrs['type'] == 'submit':
        continue
      print('cant find name: ')
      print(input.attrs)
      print(input)
    else:
      # Attempt to pull the value out or use empty for default
      value = ''
      if 'value' in input.attrs:
        value = input.attrs['value']        
      data[input.attrs['name']] = value
  
  # Data is built, ask for user/pass
  print('Please login to Canvas')
  data['username'] = raw_input('Enter your NetID: ')
  data['password'] = getpass.getpass('Enter your password: ')
  
  r = s.post('https://webauth.usf.edu'+webAuth.attrs['action'], data=data)
  
  if r.url.find('webauth.usf.edu') >= 0:
    return False
  
  # Save this cookie jar
  with open(cookieJar, 'w') as f:
    pickle.dump(requests.utils.dict_from_cookiejar(s.cookies), f)
  
  # By now we're logged in
  return True

# Asks user what the presentation URL is, then downloads it into a file
# s = session
def downloadPresentation(s):
  # Ask for the presentation url
  presUrl = raw_input('Gimmie a presentation url: ')

  # Request presentation, the final url will be the working url to get frame.xml
  pres = s.get(presUrl)

  workingUrl = pres.url[:pres.url.rfind('/')]
  
  # Jackpot is /story_content/frame.xml > yank all the <slidetranscript> elements
  frameUrl = workingUrl + '/story_content/frame.xml'
  frame = s.get(frameUrl, allow_redirects=False)
  
  # Sometimes frame.xml is hiding in presentation_content
  if not frame.ok:
    frameUrl = workingUrl + '/presentation_content/frame.xml'
    frame = s.get(frameUrl, allow_redirects=False)

  if not frame.ok:
    print('FAILURE: Could not get frame.xml, OH NO!')
    print(frame.content)
    print(frameUrl)
    print('-->')
    print(frame.url)
    return False  
  
  # Verify file is legit (kinda wonky)
  if frame.url.find('webauth.usf.edu') >= 0:
    # Crap hit the fan, the session is dead on canvas
    # But the session will turn legit from USF's end (or something)
    # We delete the old cookies, and return false to prompt a re-login
    os.remove(cookieJar)
    print('You\'re not logged in!')
    print(frame.content)
    print(frameUrl)
    print('-->')
    print(frame.url)
    return False
  
  
    
  # Parse the page
  bsFrame = newBS(frame.content)

  # transcripts is a list of transcripts 
  #transcripts = BeautifulSoup(frame.content, parse_only=SoupStrainer('slidetranscript')).contents
  transcripts = bsFrame.find_all('slidetranscript')

  # lines will store the final output
  lines = ''
  for transcript in transcripts:

    #transcripts contain inner html that BS hasn't rendered
    inner = newBS(transcript.text).get_text()
    lines = lines + inner + "\r\n\r\n"
    
  #print(lines.encode('utf-8'))  
  #print(' ')
  
  filename = time.strftime("%Y%m%d-%H%M%S") + '.txt'
  try:
    filename = bsFrame.find('option', {'name':'title_text'}).attrs['value']
    filename = fix_filename(filename) + '.txt'
  except AttributeError:
    pass
  
  #output dir
  try:
    os.mkdir('presentations')
  except OSError:
    pass
  
  output = codecs.open('presentations/' + filename, 'w', 'utf-8')
  output.write(strip_gremlins(lines))
  output.close()

  print('')
  print('wrote '+str(len(transcripts))+' slides to ' + filename)
  
  return True
  
#Converts unsafe filenames to safe ones  
def fix_filename(s):
  return s.replace(':','-').replace('<','').replace('>','').replace('"',"'")\
    .replace('/','').replace('\\','').replace('|','').replace('?','')\
    .replace('*','').replace(' ','_')


# http://stackoverflow.com/questions/16694907/how-to-download-large-file-in-python-with-requests-py
def download_file(url):
    local_filename = url.split('/')[-1]
    # NOTE the stream=True parameter
    r = s.get(url, stream=True)
    with open(local_filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024): 
            if chunk: # filter out keep-alive new chunks
                f.write(chunk)
                f.flush()
    return local_filename

# Converst the horrible MS Word quotes to standard
# http://nodnod.net/2009/feb/22/converting-quotes-macvim-and-python/
def strip_gremlins(s):
  s = s.replace(u"\u201c", "\"").replace(u"\u201d", "\"") #strip double curly quotes
  s = s.replace(u"\u2018", "'").replace(u"\u2019", "'").replace(u"\u02BC", "'") #strip single curly quotes
  return s
  
def doLogin(session):

  while not verifyLogin(session)[0]: 
    if login(session):
      print('Successfully logged in')
    else:
      print('Invalid User/Password, try again')

  
# MAIN
if __name__ == "__main__":
  session = getSession()

  doLogin(session)

  # Main Loop
  while True:
    
    while not downloadPresentation(session):
      print('It appears you\'re not logged in')
      doLogin(session)
    
    print('')
    result = raw_input('Press [Enter] to go again, or q + [Enter] to quit: ')
    
    if result == 'q':
      break;
