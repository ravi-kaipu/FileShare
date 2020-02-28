import http.server
import socketserver
import os
from datetime import datetime
import tkinter as tk
import tkinter.filedialog
import socket
import threading
import json
import re
import requests
import shutil
import time
try:
    import Tkinter
    import ttk
except ImportError:  # Python 3
    import tkinter as Tkinter
    import tkinter.ttk as ttk
PORT = 8010

class CustomedServer(http.server.SimpleHTTPRequestHandler):
    def extract_params(self, st, params = {}):
        if not "&" in st:
            words = [st[2:]]
        else:
            words = st[2:].split("&")
        for word in words:
            if not "=" in word:
                continue
            else:
                k, v = word.split("=")
                params[k] = v

        return params

    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
    def do_HEAD(self):
        self._set_headers()
        
    def do_GET(self):
        self._set_headers()
        self.handle_client_request(self.query)
        
    def do_POST(self):
        ctype, pdict = cgi.parse_header(self.headers.getheader('content-type'))
        
        # refuse to receive non-json content
        if ctype != 'application/json':
            self.send_response(400)
            self.end_headers()
            return
            
        # read the message and convert it into a python dictionary
        length = int(self.headers.getheader('content-length'))
        message = json.loads(self.rfile.read(length))
        
        # add a property to the object, just to mess with data
        message["received"] = "ok"
        
        # send the message back
        self._set_headers()
        self.wfile.write(json.dumps(message))

    def handle_one_request(self):
        try:
            self.raw_requestline = self.rfile.readline(65537)
            if len(self.raw_requestline) > 65536:
                self.requestline = ''
                self.request_version = ''
                self.command = ''
                self.send_error(414)
                return
            if not self.raw_requestline:
                self.close_connection = 1
                return
            if not self.parse_request():
                # An error code has been sent, just exit
                return
            mname = 'do_' + self.command
            if not hasattr(self, mname):
                self.send_error(501, "Unsupported method (%r)" % self.command)
                return
            self.query = self.path
            method = getattr(self, mname)
            method()
            self.wfile.flush() #actually send the response if not already done.
        except socket.timeout as e:
            #a read or a write timed out.  Discard this connection
            self.log_error("Request timed out: %r", e)
            self.close_connection = 1
            return
    
class MyServer(CustomedServer):
    friendlistfile = os.path.join(os.path.join(os.path.expanduser("~"), ".filesharing"), ".userinfo.json")
    sharedinfofile = os.path.join(os.path.join(os.path.expanduser("~"), ".filesharing"), ".sharedinfo.json")
    notificationfile = os.path.join(os.path.join(os.path.expanduser("~"), ".filesharing"), ".notifications.json")

    def handle_client_request(self, request):
        """
        if request == "/":
            message = "Welcome to Home\n"
            self.wfile.write(message.encode())
        """
        params = self.extract_params(str(request))
        for k, v in params.items():
            if k == "query":
                if v == "get_shared_files":
                    results = self.send_user_shared_files(self.address_string())
                    r = json.dumps(results)
                    self.wfile.write(r.encode())
                
                elif v == "download_file":
                    shared_files = self.get_user_shared_files(self.address_string())
                    filename = params["filename"]
                    for file in shared_files:
                        if filename in file["filename"]:
                            with open(file["filepath"], "rb") as fp:
                                data = fp.read()
                                self.wfile.write(data)
                elif v == "notification":
                    details = {"eventname": params["eventname"], "eventowner":params["eventowner"], "eventtime": params["eventime"]}
                    json_data = {}
                    if os.path.exists(self.notificationfile):
                        with open(self.notificationfile, "r") as fp:
                            data = fp.read()
                            json_data = json.loads(data)
                            if "notifications" in json_data:
                                notifications = json_data["notifications"]
                                json_data["notifications"] = [details]+notifications
                            else:
                                json_data["notifications"] = [details]
                    else:
                        json_data["notifications"] = [details]
                    with open(self.notificationfile, "w") as fp:
                        json.dump(json_data, fp)

    def get_shared_files(self):
        if not os.path.exists(self.sharedinfofile):
            return []
        with open(self.sharedinfofile, "r") as jf:
            json_data = json.loads(jf.read())
            if "shared_files" in json_data:
                results = json_data["shared_files"]
                return results
            return []

    def get_user_shared_files(self, client_address):
        if not os.path.exists(self.sharedinfofile):
            return []
        with open(self.sharedinfofile, "r") as jf:
            json_data = json.loads(jf.read())
        results = json_data["shared_files"]
        out_json = []
        for file in results:
            if "all" in file["users"] or client_address in file["users"]:
                out_json.append(file)
        return out_json
    
    def send_user_shared_files(self, client_address):
        out_json = []
        for file in self.get_user_shared_files(client_address):
            filed = {}
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            myipaddr = s.getsockname()[0]
            filed["filename"] = file["filename"]
            filed["uploadtime"] = file["uploadtime"]
            filed["filesize"] = file["filesize"]
            filed["owner"] = myipaddr
            out_json.append(filed)
        return out_json

    def get_data(self, param):
        if not os.path.exists(self.friendlistfile):
            return []
        #json manipulation
        with open(self.friendlistfile, "r") as fp:
            json_data = json.loads(fp.read())
        results = dict(json_data)
        return results[param] if param in results else []
    
    def find_friend(self, ipaddr):
        for friend in self.allfriends():
            if friend["ipaddr"] == ipaddr:
                return friend
        return {}

    def allfriends(self):
        friends = self.get_data("friends")
        self.friends = friends
        return friends

    def inform_friends(self, details):
        friends = self.allfriends()
        for friend in friends:
            self.populate_info(friend, details)
        print ("all the friends were informed")

    def populate_info(self, friend, message):
        url = "http://{}:{}".format(friend["ipaddr"], PORT)
        params = {"query":"notification", "eventime": message["uploadtime"], "eventname": message["filename"], "eventowner":message["owner"]}
        try:
            return requests.get(url, params=params, timeout=2)
        except:
            pass

    def save_in_sharedinfo(self, details):
        json_data = {}
        if os.path.exists(self.sharedinfofile):
            with open(self.sharedinfofile, "r") as fp:
                data = fp.read()
                json_data = json.loads(data)
                if "shared_files" in json_data:
                    sfiles = json_data["shared_files"]
                    for file in sfiles:
                        if file["filename"] == details["filename"]:
                            return
                    json_data["shared_files"] = sfiles + [details]
                else:
                    json_data["shared_files"] = [details]
        else:
            json_data["shared_files"] = [details]
        with open(self.sharedinfofile, "w") as fp:
            json.dump(json_data, fp)

    def share_file(self, filepath, users = []):
        fname = os.path.basename(filepath)
        fsize = os.path.getsize(filepath)
        nowtime = datetime.now()
        uploadtime = nowtime.strftime("%Y-%m-%d %H:%M:%S")
        if not users:
            users = ["all"]
            """
            friends = self.allfriends()
            users = [self.myipaddr, "127.0.0.1"]
            for f in friends:
                users.append(f["ipaddr"])
            users = list(set(users))
            """
        details = {"filename": fname, "filepath": filepath, "filesize": fsize, "uploadtime": uploadtime,
                "owner": "127.0.0.1", "users": users}
        self.save_in_sharedinfo(details)
        self.inform_friends(details)

    def unshare_file(self, details):
        filename = details["filename"]
        with open(self.sharedinfofile, "r") as fp:
            data = fp.read()
            json_data = json.loads(data)
            if "shared_files" in json_data:
                shared_files = json_data["shared_files"]
                final = []
                for file in shared_files:
                    if file["filename"] == filename:
                        shared_files.remove(file)
                json_data["shared_files"] = shared_files

        with open(self.sharedinfofile, "w") as fp:
            json.dump(json_data, fp)

    def run_as_server(self):
        server = socketserver.TCPServer(("", PORT), MyServer)
        print("Server started at ip {} port {} ".format(self.myipaddr, PORT))
        #execute as thread
        t = threading.Thread(target=server.serve_forever, args=(), daemon=True)
        t.start()

    def establish_connection(self, ipaddr, params={"query":"get_shared_files"}):
        print("Establishing connection with ip {}".format(ipaddr))
        st = "http://{}:{}".format(ipaddr, PORT, params)
        try:
            r = requests.get(st, params=params, stream=True, timeout=3)
            return r
        except:
            return {}


class LoginWindow(tk.Frame):
    def __init__(self, parent, controller):
        self.parent = parent
        self.controller = controller
        self.is_packed = True
        tk.Frame.__init__(self, parent, width=1000,  height=500, bd=2)
        
        if os.path.exists(self.controller.friendlistfile):
            self.controller.show_frame(FriendsWindow)
            return

        heading = tk.Label(self, text="Registration", font=("Arial", 14, "bold")) 
        first_name = tk.Label(self, text="First Name") 
        last_name = tk.Label(self, text="Last Name") 
        email_id = tk.Label(self, text="Email id") 
 
        heading.grid(row=0, column=1) 
        first_name.grid(row=1, column=0) 
        last_name.grid(row=2, column=0) 
        email_id.grid(row=3, column=0) 
    
        self.name_field = tk.Entry(self) 
        self.last_field = tk.Entry(self) 
        self.email_id_field = tk.Entry(self) 
    
        self.name_field.grid(row=1, column=1, ipadx="100") 
        self.last_field.grid(row=2, column=1, ipadx="100") 
        self.email_id_field.grid(row=3, column=1, ipadx="100") 

        submit = tk.Button(self, text="Submit", fg="white", 
                            bg="Blue", cursor = "hand2", command=self.insert) 
        submit.grid(row=10, column=1) 

        error_field = tk.Label(self, text="", fg="red")
        error_field.grid(row=13, column=1, sticky=tk.S)
        
        self.error_field = error_field

    def register_user(self, fullname, email_id):
        userdata = {"name": fullname, "email": email_id, "ipaddr":self.controller.myipaddr}
        main_data = {}
        main_data["userdetails"] = userdata
        with open(self.controller.friendlistfile, "w") as outfile:
            json.dump(main_data, outfile)
    
    def validate_email(self, email_id):
        regex = '^\w+([\.-]?\w+)*@\w+([\.-]?\w+)*(\.\w{2,3})+$'
        if (re.search(regex, email_id)):
            return True
        return False

    def insert(self):
        name_field = self.name_field.get()
        last_field = self.last_field.get()
        email_id_field = self.email_id_field.get()
        if name_field and last_field and email_id_field and self.validate_email(email_id_field):
            fullname = name_field + " " + last_field
            self.register_user(fullname, email_id_field)
            self.forget()
            self.controller.show_frame(FriendsWindow)
        else:
            if not name_field:
                text = "ERROR: First name is required"
                self.name_field.focus_set()
            elif not last_field:
                text = "ERROR: Last name is required"
                self.last_field.focus_set()
            elif not email_id_field or not self.validate_email(email_id_field):
                text = "ERROR: Email is required"
                self.email_id_field.focus_set()
            else:
                text = "ERROR: First name is required"
                self.name_field.focus_set()
            self.error_field.config(text=text, font=("sans", 12, "bold"))
        return False
    
    def show(self):
        #self.grid(row=0,column=0,sticky="nsew")
        self.pack()

class AddFriend(tk.Frame):
    def __init__(self, parent, controller):
        self.parent = parent
        self.controller = controller
        self.is_packed = True
        tk.Frame.__init__(self, parent)
        heading = tk.Label(self, text="Add Friend", font=("Arial", 14)) 
        heading.grid(row=0, column=1) 
        label = tk.Label(self, text = "IP address ")
        label.grid(row=1, column=0, sticky=tk.E)

        self.ipaddr = tk.Entry(self)
        self.ipaddr.grid(row=1, column=1)

        label1 = tk.Label(self, text = "Friend name ")
        label1.grid(row=2, column=0, sticky=tk.E)

        self.friend_name = tk.Entry(self)
        self.friend_name.grid(row=2, column=1)

        submit = tk.Button(self, text="Submit", fg="Black", 
                            bg="white", command=self.insert, cursor="hand2") 
        submit.grid(row=4, column=0, columnspan=3) 

        cancel_btn = tk.Button(self, text="Cancel", fg="white", 
                            bg="purple", command=self.cancel_window, cursor="hand2") 
        cancel_btn.grid(row=4, columnspan=2, column=0, sticky=tk.NE, pady=2)
        error_field = tk.Label(self, text="", font= ("sans", 12, "bold"), fg="red")
        error_field.grid(row=5, column=1)
        self.error_field = error_field
        self.remove_friend_button = tk.Button(self, text="Remove friend", cursor="hand2", bg="orange", command=self.remove_friend)
    
        self.remove_friend = tk.Label(self, text="FriendsList", font=("times", 14, "bold"))
        self.remove_friend.grid(row=6, column=1)

        self.main_page = tk.Button(self, text="<< Back", cursor="hand2", bg="orange", fg="white", command=self.controller.main_page)
        self.main_page.grid(row=6, column=0, sticky=tk.W)

        self.tree = ttk.Treeview(self,
                                 columns=('S.No', 'Friend Name'), height=18)
        self.tree.heading('#1', text='Friend Name')
        self.tree.heading('#2', text='IP Address')
        self.tree.heading('#0', text='S.No')
        self.tree.column('#2', stretch=Tkinter.YES, width=150)
        self.tree.column('#1', stretch=Tkinter.YES, width=250)
        self.tree.column('#0', stretch=Tkinter.YES, width=70)
        self.tree.grid(row=13, columnspan=3, sticky='nsew', pady=1)
        self.treeview = self.tree
        
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        vsb.place(x=460, y=150, height=386)

        self.tree.configure(yscrollcommand=vsb.set)

        i = 1
        v = tk.IntVar()
        self.tree.bind('<<TreeviewSelect>>', self.show_remove_button)
        self.friends = self.controller.allfriends()
        for file in self.friends:
            self.treeview.insert('', 'end', text=str(i),
                             values=(file["name"], file["ipaddr"]))
            i += 1
    
    def refresh_data(self):
        self.tree = ttk.Treeview(self,
                                 columns=('S.No', 'Friend Name'), height=18)
        self.tree.heading('#1', text='Friend Name')
        self.tree.heading('#2', text='IP Address')
        self.tree.heading('#0', text='S.No')
        self.tree.column('#2', stretch=Tkinter.YES, width=150)
        self.tree.column('#1', stretch=Tkinter.YES, width=250)
        self.tree.column('#0', stretch=Tkinter.YES, width=70)
        self.tree.grid(row=13, columnspan=3, sticky='nsew', pady=1)
        self.treeview = self.tree
        
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        vsb.place(x=460, y=150, height=386)

        self.tree.configure(yscrollcommand=vsb.set)

        i = 1
        v = tk.IntVar()
        self.tree.bind('<<TreeviewSelect>>', self.show_remove_button)
        self.friends = self.controller.allfriends()
        for file in self.friends:
            self.treeview.insert('', 'end', text=str(i),
                             values=(file["name"], file["ipaddr"]))
            i += 1

    def show_remove_button(self, event):
        self.remove_friend_button.grid(row=6, column=2, sticky=tk.E)

    def remove_friend(self):
        item = self.tree.selection()
        if not item:
            return
        item = item[0]
        friend = self.friends[int(self.tree.item(item,"text"))-1]
        self.friends.remove(friend)
        with open(self.controller.friendlistfile, "r") as fp:
            data = fp.read()
            json_data = json.loads(data)
            json_data["friends"] = self.friends
        
        with open(self.controller.friendlistfile, "w") as fp:
            json.dump(json_data, fp)
        
        self.refresh_data()
        self.remove_friend_button.grid_forget()
        
    def validate_ipaddr(self, addr):
        r = re.search(r'(\d+).(\d+).(\d+).(\d+)', addr)
        if r:
            return True if len(r.group(0)) == len(addr) else False
        return False

    def cancel_window(self):
        self.forget()
        self.controller.frames[FriendsWindow] = FriendsWindow(self.parent, self.controller)
        self.controller.show_frame(FriendsWindow)
    
    def is_friend_exists(self, ipaddr, fname):
        for friend in self.controller.allfriends():
            if friend["ipaddr"] == ipaddr:
                return True
            elif friend["name"] == fname:
                return True
        return False

    def insert(self):
        ipaddr = self.ipaddr.get()
        friend_name = self.friend_name.get()
        if ipaddr and friend_name:
            if not self.validate_ipaddr(ipaddr):
                text = "ERROR: IP Address is invalid"
                self.error_field.config(text=text)
                self.ipaddr.focus_set()
                return
            if self.is_friend_exists(ipaddr, friend_name):
                self.error_field.config(text="ERROR: Friend is already exists", font=("arial", 11), fg="red")
                return
            self.error_field.config(text="")
            self.add_friend(ipaddr, friend_name)
            #self.forget()
            self.refresh_data()
            #self.controller.frames[FriendsWindow] = FriendsWindow(self.parent, self.controller)
            #self.controller.show_frame(FriendsWindow)
        else:
            if not ipaddr:
                text = "ERROR: IP Address is empty"
                self.ipaddr.focus_set()
            elif not friend_name:
                text = "ERROR: Friend name is empty"
                self.friend_name.focus_set()
            self.error_field.config(text=text)
            return False

    def show(self):
        self.pack()
    
    def activate(self):
        for frame, v in self.controller.frames.items():
            if frame == AddFriend:
                continue
            v.forget()
        self.show()
        self.tkraise()

    def add_friend(self, ipaddr, fname):
        details = {"name":fname, "ipaddr":ipaddr}
        final = {}
        with open(self.controller.friendlistfile, "r") as f:
            data = f.read()
            json_data = json.loads(data)
            if "friends" in json_data:
                total_list = json_data["friends"]
                json_data["friends"] = total_list + [details]
            else:
                json_data["friends"] = [details]
        with open(self.controller.friendlistfile, "w") as fp:
            json.dump(json_data, fp)

class AddFile(tk.Frame):
    def __init__(self, parent, controller):
        self.parent = parent
        self.controller = controller
        self.is_packed = True
        tk.Frame.__init__(self, parent)
        self.sf_frame = tk.Frame(self, bd=1, relief=tk.RIDGE, width=self.controller.sf_width+100, height=self.controller.sf_height, bg="yellow")
        self.sf_frame.pack(side=tk.BOTTOM)

        self.add_file = tk.Button(self, text="Add File", cursor="hand2", bg="yellow", fg="black", command=self.openfilemenu)
        self.add_file.pack(side=tk.RIGHT)

        self.main_page = tk.Button(self, text="<< Back", cursor="hand2", bg="orange", fg="white", command=self.controller.main_page)
        self.main_page.pack(side=tk.LEFT)

        label = tk.Label(self, text = "Shared Files", font=("Times", 14, "bold"), fg="Blue")
        label.pack(side=tk.LEFT, padx=10)

        self.label1 = tk.Button(self, text="Remove File", bg="red", fg="white", command=self.unshare_current_file)
    
        self.tree = ttk.Treeview(self.sf_frame,
                                 columns=('Dose', 'Modification date',  'S.No'), height=23)
        self.tree.heading('#1', text='Filename')
        self.tree.heading('#2', text='Filesize')
        self.tree.heading('#3', text='Shared time')
        self.tree.heading('#0', text='S.No')
        self.tree.column('#2', stretch=Tkinter.YES, width=100)
        self.tree.column('#1', stretch=Tkinter.YES, width=350)
        self.tree.column('#3', stretch=Tkinter.YES, width=130)
        self.tree.column('#0', stretch=Tkinter.YES, width=70)
        self.tree.grid(row=4, columnspan=4, sticky='nsew')
        self.treeview = self.tree
        
        vsb = ttk.Scrollbar(self.sf_frame, orient="vertical", command=self.tree.yview)
        vsb.place(x=645, y=1, height=self.controller.sf_height-20)

        self.tree.configure(yscrollcommand=vsb.set)

        i = 1
        v = tk.IntVar()
        self.tree.bind('<<TreeviewSelect>>', self.show_remove_button)
        
        shared_files = self.controller.get_shared_files()
        self.shared_files = shared_files
        for file in shared_files:
            self.treeview.insert('', 'end', text=str(i),
                             values=(file["filename"], file["filesize"],  file["uploadtime"]))
            i += 1
        
    def refresh_data(self):
        self.tree = ttk.Treeview(self.sf_frame,
                                 columns=('Dose', 'Modification date', 'S.No'),  height=23)
        self.tree.heading('#1', text='Filename')
        self.tree.heading('#2', text='Filesize')
        self.tree.heading('#3', text='Shared time')
        self.tree.heading('#0', text='S.No')
        self.tree.column('#2', stretch=Tkinter.YES, width=100)
        self.tree.column('#1', stretch=Tkinter.YES, width=350)
        self.tree.column('#3', stretch=Tkinter.YES, width=130)
        self.tree.column('#0', stretch=Tkinter.YES, width=70)
        self.tree.grid(row=4, columnspan=4, sticky='nsew')
        self.treeview = self.tree
        
        vsb = ttk.Scrollbar(self.sf_frame, orient="vertical", command=self.tree.yview)
        vsb.place(x=645, y=1, height=self.controller.sf_height-20)

        i = 1
        v = tk.IntVar()
        self.tree.bind("<<TreeviewSelect>>", self.show_remove_button)
        
        self.shared_files = self.controller.get_shared_files()
        
        for file in self.shared_files:
            self.treeview.insert('', 'end', text=str(i),
                             values=(file["filename"], file["filesize"], file["uploadtime"]))
            i += 1

    def show_remove_button(self, event):
        if len(self.shared_files) > 0 and self.tree.selection():
            self.label1.pack(side=tk.RIGHT, padx=10)

    def unshare_current_file(self):
        item = self.tree.selection()
        if not item:
            return
        item = item[0]
        itemd = self.shared_files[int(self.tree.item(item,"text"))-1]
        self.controller.unshare_file(itemd)
        self.refresh_data()
        self.label1.pack_forget()

    def openfilemenu(self):
        filename = tk.filedialog.askopenfilename()
        if filename:
            self.controller.share_file(filename, users=[])
        self.refresh_data()

    def show(self):
        self.pack()

    def activate(self):
        for frame, v in self.controller.frames.items():
            if frame == AddFile:
                continue
            v.forget()
        
        self.show()
        self.tkraise()

class Notifications(tk.Frame):
    def __init__(self, parent, controller):
        self.parent = parent
        self.controller = controller
        self.is_packed = True
        tk.Frame.__init__(self, parent)

        self.nc_frame = tk.Frame(self, bd=1, relief=tk.RIDGE, width=self.controller.fl_width, height=self.controller.fl_height, bg="red")
        self.nc_frame.pack(anchor="ne", fill="both", side=tk.LEFT)

        self.main_page = tk.Button(self.nc_frame, text="<< Back", cursor="hand2", bg="orange", fg="white", command=self.controller.main_page)
        self.main_page.pack(side=tk.LEFT, anchor="ne")

        if not os.path.exists(self.controller.notificationfile):
            return
        with open(self.controller.notificationfile, "r") as fp:
            data = fp.read()
            json_data = json.loads(data)
            i = 0
            for ev in json_data["notifications"]:
                timeframe = re.search("(\d+)-(\d+)-(\d+)\+(\d+)%3A(\d+)%3A(\d+)", ev["eventtime"])
                timeframe1 = timeframe.group(1)+ "-" + timeframe.group(2)+ "-" + timeframe.group(3)
                timeframe = timeframe1 + " " + timeframe.group(4) + ":" + timeframe.group(5) + ":" + timeframe.group(6)
                friend = self.controller.find_friend(ev["eventowner"])
                owner = ev["eventowner"]
                if  friend:
                    owner = friend['name']
                    
                fame = "* " + owner + " added a new file " + ev["eventname"] + " at " + timeframe + "\n"
                label = tk.Label(self.nc_frame, text=fame, font=("arial", 12), width = 150)
                label.pack()
                
                i += 1

    def show(self):
        self.pack(side=tk.TOP)       

    def activate(self):
        for frame, v in self.controller.frames.items():
            if frame == Notifications:
                continue
            v.forget()
        self.show()
        self.tkraise()

class FriendsWindow(tk.Frame, MyServer):
    def __init__(self, parent, controller):
        self.parent = parent
        self.controller = controller
        self.is_packed = True
        tk.Frame.__init__(self, parent)

        fl_frame = tk.Frame(self, bd=1, relief=tk.RIDGE, width=self.controller.fl_width, height=self.controller.fl_height, bg="red")
        friend_label = tk.Label(fl_frame, text="Friends", font = ("Arial", 14), bg="orange",fg="white", width=23, bd=3, relief = tk.RAISED)
        friend_label.pack()
        
        lb = tk.Listbox(fl_frame, font=("Times", 13), width=29, height=25, bd=0, selectmode=tk.BROWSE, cursor = "hand2")
        num = 1
        for friend in self.allfriends():
            lb.insert(num, " "+friend["name"].capitalize())
            num += 1

        lb.bind("<<ListboxSelect>>", self.onFriendSelect)
        lb.pack()
    
        fl_frame.pack(side=tk.LEFT)        

        self.sf_frame = tk.Frame(self, bd=1, relief=tk.RIDGE, width=self.controller.sf_width, height=self.controller.sf_height, bg="yellow")
        self.sf_frame.pack()

        self.download_button = tk.Button(self, text = "Download", font=("Times", 10, "bold"), bg="red", fg="white", cursor = "hand2", command=self.download_file)

        textv= "Server started at IP {} port {}".format(self.controller.myipaddr, PORT)
        serverlabel = tk.Label(self, text = textv, width=85, bd=2, fg="orange", justify=tk.LEFT, font=("Times", 12))
        serverlabel.pack(side=tk.BOTTOM)
        self.downloadedlabel = tk.Label(self, text = textv, width=95, wraplength=self.controller.sf_width-30, bd=2, fg="blue", justify=tk.LEFT, font=("Times", 12))
    
        self.tree = ttk.Treeview(self.sf_frame,
                                 columns=('Dose', 'Modification date', 'Owner', 'S.No'), height=23)
        self.tree.heading('#1', text='Filename')
        self.tree.heading('#2', text='Filesize')
        self.tree.heading('#3', text='Owner')
        self.tree.heading('#4', text='Shared time')
        self.tree.heading('#0', text='S.No')
        self.tree.column('#2', stretch=Tkinter.YES, width=90)
        self.tree.column('#3', stretch=Tkinter.YES, width=100)
        self.tree.column('#1', stretch=Tkinter.YES, width=320)
        self.tree.column('#4', stretch=Tkinter.YES, width=130)
        self.tree.column('#0', stretch=Tkinter.YES, width=40)
        self.tree.grid(row=4, columnspan=4, sticky='nsew')
        self.treeview = self.tree


    def display_shared_files(self, friend, shared_files):
        self.download_button.pack_forget()
        self.tree = ttk.Treeview(self.sf_frame,
                                 columns=('Dose', 'Modification date', 'Owner', 'S.No'))
        self.tree.heading('#1', text='Filename')
        self.tree.heading('#2', text='Filesize')
        self.tree.heading('#3', text='Owner')
        self.tree.heading('#4', text='Shared time')
        self.tree.heading('#0', text='S.No')
        self.tree.column('#2', stretch=Tkinter.YES, width=90)
        self.tree.column('#3', stretch=Tkinter.YES, width=100)
        self.tree.column('#1', stretch=Tkinter.YES, width=320)
        self.tree.column('#4', stretch=Tkinter.YES, width=130)
        self.tree.column('#0', stretch=Tkinter.YES, width=40)
        self.tree.grid(row=4, columnspan=4, sticky='nsew')
        self.treeview = self.tree
        
        vsb = ttk.Scrollbar(self.sf_frame, orient="vertical", command=self.tree.yview)
        vsb.place(x=670, y=1, height=self.controller.sf_height-20)

        self.tree.configure(yscrollcommand=vsb.set)

        i = 1
        v = tk.IntVar()
        self.tree.bind("<<TreeviewSelect>>", self.OnDoubleClickFileMenu)
        
        self.shared_files = shared_files
        
        for file in shared_files:
            self.treeview.insert('', 'end', text=str(i),
                             values=(file["filename"], file["filesize"], file["owner"], file["uploadtime"]))
            i += 1

    def show(self):
        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Add Friend", command=self.controller.frames[AddFriend].activate)
        filemenu.add_command(label="Share File", command=self.controller.frames[AddFile].activate)
        filemenu.add_command(label="Notifications", command=self.controller.frames[Notifications].activate)        
        self.controller.config(menu=filemenu)
        self.pack(side=tk.LEFT)   
    
    def get_contents(self, ipaddr):
        conn = self.establish_connection(ipaddr)
        shared_files = self.fetch_results(conn)
        if shared_files:
            return shared_files
        return []
        
    def show_download_button(self):
        self.downloadedlabel.pack_forget()
        self.download_button.pack()
        
    def OnDoubleClickFileMenu(self, event):
        self.show_download_button()
    
    def download_file(self):
        item = self.tree.selection()
        if not item:
            return
        item = item[0]
        itemd = self.shared_files[int(self.tree.item(item,"text"))-1]
        filedata = self.get_file_data(itemd)
        out_file = "downloads"
        os.makedirs(out_file, exist_ok=True)
        out_file = os.path.join("downloads",itemd["filename"])
        with open(out_file, "wb") as outfile:
            shutil.copyfileobj(filedata.raw, outfile)
        del filedata
        self.download_button.pack_forget()
        downloadedtext = "Downloaded \"{}\"".format(itemd["filename"])
        self.downloadedlabel.config(text=downloadedtext)
        self.downloadedlabel.pack(side=tk.LEFT, anchor="w", padx=10, fill=tk.X)

    def onFriendSelect(self, val):
        sender = val.widget
        idx = sender.curselection()
        if not idx:
            return
        idx = idx[0]
        friend = self.friends[idx]
        ipaddr = friend["ipaddr"]
        shared_files = self.get_contents(ipaddr)
        self.display_shared_files(friend, shared_files)
   
    def fetch_results(self, conn):
        """
        get the json information
        """
        if conn:
            json_data = conn.json()
            return json_data
        return {}

    def get_file_data(self, filed):
        ipaddr = filed["owner"]
        filename = filed["filename"]
        params = {"query":"download_file", "filename":filename}
        conn = self.establish_connection(ipaddr, params=params)
        return conn

class Application(tk.Tk, MyServer):
    def __init__(self, width = 100, height = 100):
        tk.Tk.__init__(self)
        self.title("FileShare")
        self.resizable(0,0)

        self.width = width
        self.height = height

        self.fl_width = 260
        self.fl_height = height - 2

        self.rb_width = 40
        self.rb_height = height - 45

        self.sf_width = width - self.fl_width - 7
        self.sf_height = height - 45

        self.set_geometry(height, width)

        hostname = socket.gethostname()    
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        self.myipaddr = s.getsockname()[0]
        self.container = tk.Frame(self)
        self.container.pack(side="top", fill="both", expand=True)

        self.frames = {}

        for F in [AddFile, AddFriend, Notifications, FriendsWindow, LoginWindow]:
            frame = F(self.container, self)
            self.frames[F] = frame

        self.show_frame(LoginWindow)
        os.makedirs(os.path.join(os.path.expanduser("~"), ".filesharing"), exist_ok=True)

    def show_frame(self, cont):
        frame = self.frames[cont]
        if frame.is_packed:
            frame.show()
        else:
            frame.tkraise()

    def set_geometry(self, height, width):
        screen_width = self.winfo_screenwidth()/5
        screen_height = self.winfo_screenheight()/5.5
        st = '%dx%d+%d+%d'%(width, height, screen_width, screen_height)
        self.geometry(st)

    def main_page(self):
        self.frames[FriendsWindow] = FriendsWindow(self.container, self)
        for f, v in self.frames.items():
            if f == FriendsWindow:
                continue
            v.forget()
        self.show_frame(FriendsWindow)

    def run(self):
        self.run_as_server()
        self.mainloop()

if __name__ == "__main__":
    app = Application(height=550, width=950)
    app['bg'] = '#49A'

    app.run()