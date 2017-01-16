#execfile('go.py')
import requests
from bs4 import BeautifulSoup
from bs4 import SoupStrainer
import getpass
import os.path
import os
import pickle
import codecs
import sys
import time
import re
import subprocess
import shutil

# Basic Config
canvasUrl = 'https://usflearn.instructure.com/'
cookieJar = 'cookies.txt'

WORKING_DIR = os.path.abspath(os.path.join(os.getcwd(),'workingdir'))

regSwfXml = r"(\<\?xml.+)((?<!\\)\;|$)"

FFDEC_DIR = 'ffdec_10.0.0'

if os.name == 'nt': # Windows
  FFDEC_RUN = os.path.join(FFDEC_DIR, 'ffdec.bat')
else:
  FFDEC_RUN = os.path.join(FFDEC_DIR, 'ffdec.sh')

FFDEC_RUN = os.path.abspath(FFDEC_RUN);

try:
  os.mkdir(WORKING_DIR)
except OSError:
  pass

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
  src_prefix = '/story_content'
  
  # Sometimes frame.xml is hiding in presentation_content
  if not frame.ok:
    frameUrl = workingUrl + '/presentation_content/frame.xml'
    frame = s.get(frameUrl, allow_redirects=False)
    src_prefix = '/presentation_content'

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

  # Find all slides we link 
  # <slidelink slideid="4pForxcLIQM.6LvdiZk9aLv" displaytext="Definitions of Intelligence" expand="false" type="slide"/>
  slideIds = [sl['slideid'] for sl in bsFrame.select('nav_data > outline > links > slidelink')]

  # transcripts is a list of transcripts 
  #transcripts = BeautifulSoup(frame.content, parse_only=SoupStrainer('slidetranscript')).contents
  transcripts = bsFrame.find_all('slidetranscript')

  # lines will store the final output
  lines = ''
  for transcript in transcripts:
    clearWorkingDir()

    #transcripts contain inner html that BS hasn't rendered
    inner = newBS(transcript.text).get_text()
    lines = lines + inner

    if transcript['slideid'] not in slideIds:
      # Ok we have a transcript that's not a direct page. 
      # This means it's some page's sub-content.
      # The only way I know of to get this content is to 
      # extract it out of the linked .swf
      # Here we go.
      endId = transcript['slideid'].split('.')[-1]
      url = workingUrl + src_prefix + ('/slides/%s.swf' % endId)
      print ('%s is sub-content, trying to get swf for transcript @ %s' % (endId, url))

      swf = download_file(s, url, 'tmp.swf', WORKING_DIR)

      swfText = ''
      try:
        subprocess.check_call([FFDEC_RUN, '-export', 'script', WORKING_DIR, os.path.join(WORKING_DIR, 'tmp.swf')])

        for theFile in os.listdir(os.path.join(WORKING_DIR, 'scripts')):
          with open(os.path.join(WORKING_DIR, 'scripts', theFile), 'r') as f:
            matches = re.search(regSwfXml, f.read())

          if matches and len(matches.groups()) == 2:
            xml = matches.group(1)
            bs = newBS(xml)
            # Get all the alttext elements
            altels = bs.find_all(alttext=True)
            for tt in altels:
              swfText += tt['alttext'] + os.linesep;

      except subprocess.CalledProcessError:
        print ('ERROR processing %s' % endId);
        swfText = None
      except OSError:
        print ('No swf for %s' % endId);

      clearWorkingDir()

      if swfText:
        lines += os.linesep + swfText

    lines += os.linesep*2
  
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
def download_file(s, url, local_filename=None, path=None):
    if local_filename is None:
      local_filename = url.split('/')[-1]

    local_filename = fix_filename(local_filename);
    
    if path is None:
      path = os.getcwd()

    local_filename = os.path.abspath(os.path.join(path, local_filename));
      
    # NOTE the stream=True parameter
    r = s.get(url, stream=True)
    with open(local_filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024): 
            if chunk: # filter out keep-alive new chunks
                f.write(chunk)
                f.flush()
    return local_filename


def clearWorkingDir():
  try:
    os.mkdir(WORKING_DIR)
  except OSError:
    pass

  for the_file in os.listdir(WORKING_DIR):
    file_path = os.path.join(WORKING_DIR, the_file)
    try:
      if os.path.isfile(file_path):
        os.unlink(file_path)
      elif os.path.isdir(file_path): 
        shutil.rmtree(file_path)
    except Exception as e:
      pass

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
