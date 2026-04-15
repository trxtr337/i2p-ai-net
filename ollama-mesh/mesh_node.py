"""
mesh_node.py — HTTP server for the mesh node.

Public endpoints (via I2P): info, friends, chat, feed/gossip
Local endpoints (localhost): management, status, history, feed
Ollama proxy: /api/generate, /api/chat
"""

import json
import time
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from friend_manager import FriendManager
from bot_brain import BotBrain
from feed_manager import FeedManager
from gossip import GossipEngine
from memory import Memory
from discovery import Discovery


class MeshNodeHandler(BaseHTTPRequestHandler):

    friends: FriendManager = None
    brain: BotBrain = None
    config: dict = None
    feed: FeedManager = None
    gossip_engine: GossipEngine = None
    memory: Memory = None
    discovery: Discovery = None

    # ── Utilities ──────────────────────────────────

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode())

    def do_OPTIONS(self):
        """CORS preflight for web dashboard."""
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    # ── GET ───────────────────────────────────────

    def do_GET(self):
        path = self.path

        # Public: bot info
        if path == "/api/info":
            self._json(200, {
                "name": self.brain.name,
                "model": self.brain.model,
                "greeting": self.brain.greeting,
                "version": "1.0",
            })
            return

        # Local: friends list
        if path == "/api/friends":
            out = []
            for b32, info in self.friends.list_friends().items():
                out.append({
                    "name": info["name"],
                    "model": info["model"],
                    "address_short": b32[:20] + "...",
                    "address": b32,
                    "port": info["local_port"],
                    "added": info["added_at"],
                    "last_chat": info.get("last_chat"),
                })
            self._json(200, {"friends": out})
            return

        # Local: pending requests
        if path == "/api/friends/pending":
            out = []
            for b32, info in self.friends.list_pending().items():
                out.append({
                    "address": b32,
                    "name": info["name"],
                    "model": info["model"],
                    "greeting": info.get("greeting", ""),
                    "received": info["received_at"],
                })
            self._json(200, {"pending": out})
            return

        # Local: conversation history
        if path.startswith("/api/chat/history/"):
            peer_name = path.split("/")[-1]
            history = self.brain.load_conversation(peer_name)
            self._json(200, {"peer": peer_name, "messages": history[-50:]})
            return

        # Local: node status
        if path == "/api/status":
            feed_stats = self.feed.stats() if self.feed else {}
            self._json(200, {
                "bot_name": self.brain.name,
                "model": self.brain.model,
                "total_friends": len(self.friends.list_friends()),
                "pending_requests": len(self.friends.list_pending()),
                "auto_chat": self.config["chat"]["auto_chat"],
                "feed": feed_stats,
            })
            return

        # Public: posts for gossip pull
        if path.startswith("/api/feed/since/"):
            try:
                since_ts = float(path.split("/")[-1])
            except ValueError:
                since_ts = 0
            posts = self.feed.get_posts_for_gossip(since_ts=since_ts, limit=30)
            self._json(200, {"posts": posts})
            return

        # Local: feed (all or by board)
        if path == "/api/feed" or path.startswith("/api/feed?"):
            board = None
            if "?" in path:
                params = dict(p.split("=", 1) for p in path.split("?", 1)[1].split("&") if "=" in p)
                board = params.get("board")
            posts = self.feed.get_feed(board=board, limit=30)
            self._json(200, {"posts": [p.to_dict() for p in posts]})
            return

        # Local: hot posts
        if path == "/api/feed/hot":
            posts = self.feed.get_hot(limit=15)
            self._json(200, {"posts": [p.to_dict() for p in posts]})
            return

        # Local: single post with replies
        if path.startswith("/api/feed/post/"):
            post_id = path.split("/")[-1]
            post = self.feed.get_post(post_id)
            if post:
                self._json(200, post.to_dict())
            else:
                self._json(404, {"error": "post not found"})
            return

        # Local: boards list
        if path == "/api/boards":
            boards = [b.to_dict() for b in self.feed.list_boards()]
            self._json(200, {"boards": boards})
            return

        # Local: feed stats
        if path == "/api/feed/stats":
            self._json(200, self.feed.stats())
            return

        # Local: bot goals
        if path == "/api/memory/goals":
            if self.memory:
                self._json(200, self.memory.get_goals())
            else:
                self._json(200, {})
            return

        # Local: relations
        if path == "/api/memory/relations":
            if self.memory:
                self._json(200, self.memory.get_relations())
            else:
                self._json(200, {})
            return

        # Public: public friend list for discovery
        if path == "/api/friends/public":
            if self.discovery:
                self._json(200, {"peers": self.discovery.get_public_friends_list()})
            else:
                self._json(200, {"peers": []})
            return

        # Local: discovered nodes
        if path == "/api/discovery":
            if self.discovery:
                self._json(200, {"discovered": self.discovery.list_discovered()})
            else:
                self._json(200, {"discovered": []})
            return

        self._json(404, {"error": "not found"})

    # ── POST ──────────────────────────────────────

    def do_POST(self):
        path = self.path

        # Public: incoming friend request
        if path == "/api/friends/request":
            body = self._body()
            result = self.friends.receive_request(
                from_b32=body.get("from_b32", ""),
                from_name=body.get("from_name", "Unknown"),
                from_model=body.get("from_model", "unknown"),
                greeting=body.get("greeting", ""),
            )
            self._json(200, result)
            return

        # Local: accept request
        if path == "/api/friends/accept":
            body = self._body()
            b32 = body.get("address", "")
            result = self.friends.accept(b32)

            if result["status"] == "accepted":
                threading.Thread(
                    target=_notify_accepted,
                    args=(self.friends, self.brain, self.config, b32, result["port"]),
                    daemon=True,
                ).start()

            self._json(200, result)
            return

        # Local: reject request
        if path == "/api/friends/reject":
            body = self._body()
            result = self.friends.reject(body.get("address", ""))
            self._json(200, result)
            return

        # Local: send friend request
        if path == "/api/friends/add":
            body = self._body()
            result = self.friends.send_request(
                to_b32=body.get("address", ""),
                my_b32=self.config["network"].get("my_b32", ""),
                my_name=self.brain.name,
                my_model=self.brain.model,
                greeting=self.brain.greeting,
            )
            self._json(200, result)
            return

        # Public: friendship accepted notification
        if path == "/api/friends/accepted":
            body = self._body()
            self.friends.confirm_accepted(
                from_b32=body.get("from_b32", ""),
                from_name=body.get("from_name", ""),
                from_model=body.get("from_model", ""),
            )
            self._json(200, {"status": "ok"})
            return

        # Public: incoming chat message
        if path == "/api/chat/message":
            body = self._body()
            from_name = body.get("from_name", "Unknown")
            message = body.get("message", "")
            from_b32 = body.get("from_b32", "")

            if not self.friends.is_friend(from_b32):
                self._json(403, {"error": "not a friend"})
                return

            self.brain.save_message(from_name, from_name, message)
            history = self.brain.load_conversation(from_name)
            reply = self.brain.respond_to(from_name, message, history)

            if reply:
                self.brain.save_message(from_name, self.brain.name, reply)
                self.friends.update_last_chat(from_b32)
                print("\n[" + from_name + "]: " + message)
                print("[" + self.brain.name + "]: " + reply + "\n")
                self._json(200, {"from_name": self.brain.name, "message": reply})
            else:
                self._json(500, {"error": "generation failed"})
            return

        # Public: gossip push — receive posts
        if path == "/api/feed/sync":
            body = self._body()
            my_b32 = self.config["network"].get("my_b32", "")
            new_count = 0
            for post_dict in body.get("posts", []):
                result = self.feed.receive_post(post_dict, my_b32)
                if result:
                    new_count += 1
            if new_count:
                from_short = body.get("from_b32", "")[:12]
                print("[gossip] +" + str(new_count) + " posts from " + from_short + "...")
            self._json(200, {"received": new_count})
            return

        # Public: receive reply
        if path == "/api/feed/reply":
            body = self._body()
            post_id = body.get("post_id", "")
            reply_dict = body.get("reply", {})
            result = self.feed.receive_reply(post_id, reply_dict)
            self._json(200, {"status": "ok" if result else "duplicate"})
            return

        # Local: create post
        if path == "/api/feed/post":
            body = self._body()
            post = self.feed.create_post(
                board=body.get("board", "general"),
                author_name=self.brain.name,
                author_b32=self.config["network"].get("my_b32", ""),
                title=body.get("title", ""),
                body=body.get("body", ""),
            )
            if self.gossip_engine:
                self.gossip_engine.broadcast_post(post.to_dict())
            self._json(201, post.to_dict())
            return

        # Local: reply to post
        if path == "/api/feed/post/reply":
            body = self._body()
            reply = self.feed.add_reply(
                post_id=body.get("post_id", ""),
                author_name=self.brain.name,
                author_b32=self.config["network"].get("my_b32", ""),
                body=body.get("body", ""),
                parent_reply_id=body.get("parent_reply_id"),
            )
            if reply and self.gossip_engine:
                self.gossip_engine.broadcast_reply(body["post_id"], reply.to_dict())
            if reply:
                self._json(201, reply.to_dict())
            else:
                self._json(404, {"error": "post not found"})
            return

        # Local: react to post
        if path == "/api/feed/post/react":
            body = self._body()
            ok = self.feed.react_to_post(
                post_id=body.get("post_id", ""),
                reactor_b32=self.config["network"].get("my_b32", ""),
                reaction=body.get("reaction", "upvote"),
            )
            self._json(200, {"status": "ok" if ok else "not_found"})
            return

        # Proxy to Ollama
        if path in ("/api/generate", "/api/chat"):
            body = self._body()
            try:
                r = requests.post(
                    self.config["network"]["ollama_url"] + path,
                    json=body, stream=True, timeout=300,
                )
                self.send_response(r.status_code)
                self._cors_headers()
                for k, v in r.headers.items():
                    if k.lower() not in ("transfer-encoding", "connection"):
                        self.send_header(k, v)
                self.end_headers()
                for chunk in r.iter_content(chunk_size=4096):
                    self.wfile.write(chunk)
            except Exception as e:
                self._json(502, {"error": str(e)})
            return

        self._json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        pass  # silent mode


# ── Helper functions ──────────────────────────────────

def _notify_accepted(friends, brain, config, b32, port):
    """Background task: notify peer that we accepted their request."""
    time.sleep(15)
    try:
        requests.post(
            "http://127.0.0.1:" + str(port) + "/api/friends/accepted",
            json={
                "from_b32": config["network"].get("my_b32", ""),
                "from_name": brain.name,
                "from_model": brain.model,
            },
            timeout=60,
        )
    except Exception:
        pass


def create_server(config, friends, brain, feed=None, gossip_engine=None,
                  memory=None, discovery=None):
    """Create HTTP server with all managers attached."""
    MeshNodeHandler.friends = friends
    MeshNodeHandler.brain = brain
    MeshNodeHandler.config = config
    MeshNodeHandler.feed = feed
    MeshNodeHandler.gossip_engine = gossip_engine
    MeshNodeHandler.memory = memory
    MeshNodeHandler.discovery = discovery

    port = config["network"]["listen_port"]
    server = HTTPServer(("127.0.0.1", port), MeshNodeHandler)
    print("[server] Mesh node on 127.0.0.1:" + str(port))
    return server
