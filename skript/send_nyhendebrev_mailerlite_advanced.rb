#!/usr/bin/env ruby
# frozen_string_literal: true

require "yaml"
require "date"
require "json"
require "net/http"
require "uri"

API_BASE = "https://connect.mailerlite.com/api"

def env!(key)
  v = ENV[key]
  raise "Missing required env var #{key}" if v.nil? || v.strip.empty?
  v
end

MONTHS_NN = [
  nil,
  "januar", "februar", "mars", "april", "mai", "juni",
  "juli", "august", "september", "oktober", "november", "desember"
].freeze

# vekedagar, index = Date#wday (0 = sundag, 1 = mandag, …)
WEEKDAYS_NN = %w[sundag mandag tirsdag onsdag torsdag fredag laurdag].freeze

def fmt_date_nn(date)
  "#{date.day}. #{MONTHS_NN.fetch(date.month)} #{date.year}"
end

def fmt_date_emne_nn(date)
  "#{WEEKDAYS_NN[date.wday]} #{date.day}. #{MONTHS_NN.fetch(date.month)}"
end

def http_json(method, path, token:, body: nil)
  # URI.join(base, "/groups") would replace path and drop /api – use path without leading /
  path = path.sub(/\A\//, "")
  uri = URI.join(API_BASE + "/", path)
  req =
    case method
    when :get then Net::HTTP::Get.new(uri)
    when :post then Net::HTTP::Post.new(uri)
    else
      raise "Unsupported method #{method}"
    end

  req["Authorization"] = "Bearer #{token}"
  req["Accept"] = "application/json"

  if body
    req["Content-Type"] = "application/json"
    req.body = JSON.dump(body)
  end

  res = Net::HTTP.start(uri.host, uri.port, use_ssl: true) { |http| http.request(req) }

  if res.body.nil? || res.body.strip.empty?
    return [res.code.to_i, nil]
  end
  [res.code.to_i, JSON.parse(res.body)]
rescue JSON::ParserError
  [res.code.to_i, { "message" => res.body }]
end

def verify_group_exists!(token, group_id)
  code, data = http_json(:get, "/groups?limit=100", token: token)
  unless code == 200 && data && data["data"].is_a?(Array)
    raise "Could not fetch groups (status=#{code}). Check MAILERLITE_API_TOKEN."
  end
  ids = data["data"].map { |g| g["id"].to_s }
  return if ids.include?(group_id.to_s)
  raise <<~MSG.strip
    Group ID #{group_id.inspect} not found in your account.
    Valid group IDs: #{ids.join(", ")}.
    Update MAILERLITE_GROUP_ID in GitHub Secrets (or .env) with one of these.
  MSG
end

def load_events
  raw = YAML.load_file(File.join(__dir__, "..", "_data", "kalender.yml"))
  (raw || []).filter_map do |e|
    dato = e["dato"] || e[:dato]
    next if dato.nil? || dato.to_s.strip.empty?
    date = Date.parse(dato.to_s)
    {
      "uid" => (e["uid"] || e[:uid]).to_s,
      "dato" => date,
      "start" => (e["start"] || e[:start]).to_s,
      "slutt" => (e["slutt"] || e[:slutt]).to_s,
      "tittel" => (e["tittel"] || e[:tittel]).to_s,
      "stad" => (e["stad"] || e[:stad]).to_s,
      "lenkje" => (e["lenkje"] || e[:lenkje]).to_s,
      "merknad" => (e["merknad"] || e[:merknad]).to_s
    }
  end.sort_by { |e| e["dato"] }
end

token = env!("MAILERLITE_API_TOKEN")
group_id = env!("MAILERLITE_GROUP_ID")
from_email = env!("MAILERLITE_FROM_EMAIL")
from_name = env!("MAILERLITE_FROM_NAME")
reply_to = ENV["MAILERLITE_REPLY_TO"].to_s.strip

base_url = ENV.fetch("OSLOBYGDA_BASE_URL", "https://oslobygda.no").sub(%r{/\z}, "")
trigger_uid_contains = ENV.fetch("TRIGGER_UID_CONTAINS", "pobb-")
days_before = Integer(ENV.fetch("DAYS_BEFORE_TRIGGER", "7"))
limit = Integer(ENV.fetch("UPCOMING_LIMIT", "12"))

today = Date.today

events = load_events
future = events.select { |e| e["dato"] >= today }

trigger = future.find { |e| e["uid"].include?(trigger_uid_contains) }
if trigger.nil?
  puts "No upcoming event matching trigger uid '#{trigger_uid_contains}'. Nothing to do."
  exit 0
end

trigger_date = trigger["dato"]
send_on = trigger_date - days_before
force_send = %w[1 true yes].include?(ENV["OSLOBYGDA_FORCE_SEND"].to_s.strip.downcase)

unless force_send || today == send_on
  puts "Today is #{today}, next trigger event is #{trigger_date} (send_on=#{send_on}). Not sending today. Set OSLOBYGDA_FORCE_SEND=1 to test anyway."
  exit 0
end
puts "Force send mode – sending despite send_on=#{send_on}" if force_send && today != send_on

upcoming = future.first(limit)

subject = "Neste folkemusikkpøbb er #{fmt_date_emne_nn(trigger_date)}!"
campaign_name = "Nyhendebrev – tilskipingar – #{trigger_date.iso8601}"

html_items = upcoming.map do |e|
  line = +"<strong>#{fmt_date_nn(e["dato"])}</strong>"
  line << " kl. #{e["start"]}" unless e["start"].empty?
  line << " – #{e["tittel"]}" unless e["tittel"].empty?
  line << " (#{e["stad"]})" unless e["stad"].empty?
  "<li style=\"margin:.5em 0; padding-left:.5em; border-left:3px solid #BFEAEE; list-style:none;\">#{line}</li>"
end.join("\n")

# Stil i tråd med nettsida (pastell-palett, Fraunces). Inline CSS for e-postklientar.
html = <<~HTML
  <div style="max-width:580px; margin:0 auto; font-family:Georgia,'Times New Roman',serif; color:#12110e; background:#FCF9F3; padding:24px 20px;">
    <p style="margin:0 0 4px; font-family:'Fraunces',Georgia,serif; font-weight:700; font-size:1.25em; letter-spacing:.02em;">Oslobygda kulturlag</p>
    <p style="margin:0 0 24px; font-size:.9em; color:#5a5856;">frilynt · folkeleg · litt for seint heim</p>
    <h1 style="margin:0 0 12px; font-family:'Fraunces',Georgia,serif; font-weight:650; font-size:1.5em; color:#12110e;">Komande tilskipingar</h1>
    <p style="margin:0 0 16px; line-height:1.5;">Her er det som ligg i kalenderen vår no:</p>
    <ul style="margin:0 0 20px; padding-left:0; line-height:1.6; list-style:none;">
      #{html_items}
    </ul>
    <p style="margin:0 0 8px; line-height:1.5;">
      Sjå heile kalenderen: <a href="#{base_url}/kalender/" style="color:#2f5d50; text-decoration:underline;">#{base_url}/kalender/</a><br>
      Kalender (ICS): <a href="#{base_url}/kalender.ics" style="color:#2f5d50; text-decoration:underline;">#{base_url}/kalender.ics</a>
    </p>
    <p style="margin:20px 0 0; text-align:center;">
      <a href="#{base_url}/" style="text-decoration:none;"><img src="#{base_url}/lutar/bilete/logo_oslobygda.png" alt="Oslobygda kulturlag" width="200" height="200" style="display:inline-block; width:200px; height:200px;"></a>
    </p>
  </div>
HTML

plain = +"Komande tilskipingar\n\n"
plain << "Her er det som ligg i kalenderen vår no:\n\n"
upcoming.each do |e|
  line = +"- #{fmt_date_nn(e["dato"])}"
  line << " kl. #{e["start"]}" unless e["start"].empty?
  line << " – #{e["tittel"]}" unless e["tittel"].empty?
  line << " (#{e["stad"]})" unless e["stad"].empty?
  plain << "#{line}\n"
end
plain << "\nHeile kalenderen: #{base_url}/kalender/\n"
plain << "ICS: #{base_url}/kalender.ics\n"

# Returns { "id" => campaign_id, "status" => "draft"|"ready"|"sent" } or nil.
def find_existing_campaign(token, campaign_name)
  %w[draft ready sent].each do |status|
    code, data = http_json(:get, "/campaigns?filter[status]=#{status}&limit=100", token: token)
    next unless code == 200 && data && data["data"].is_a?(Array)
    found = data["data"].find { |c| c["name"].to_s == campaign_name }
    return { "id" => found["id"].to_s, "status" => status } if found
  end
  nil
end

existing = find_existing_campaign(token, campaign_name)
if existing && existing["status"] == "sent"
  puts "Campaign '#{campaign_name}' was already sent. Not creating/sending again."
  exit 0
end

# If draft/ready, we will send it below (campaign_id set from existing).
existing_draft_or_ready = existing && %w[draft ready].include?(existing["status"])
campaign_id = existing_draft_or_ready ? existing["id"] : nil

verify_group_exists!(token, group_id)

unless campaign_id
  email_obj = {
    "subject" => subject.to_s,
    "from_name" => from_name.to_s,
    "from" => from_email.to_s,
    "content" => html.to_s
  }
  email_obj["reply_to"] = reply_to.to_s if reply_to && !reply_to.empty?

  # Use the documented Connect API payload shape: emails must be an array with one object.
  # If the account is not allowed to send custom HTML content, fallback to plain-text only.
  email_obj_str = email_obj.transform_keys(&:to_s)
  base_no_content_email = email_obj_str.reject { |k, _| k == "content" }
  base_plain_email = base_no_content_email.merge("plain_text" => plain.to_s)
  # MailerLite docs say emails should be an array with one object. Some accounts appear to validate
  # "emails.0" as an array/object in a Laravel-like way, so we try a few wire-compatible variants.
  attempts = [
    {
      "label" => "docs array+html string-group",
      "body" => {
        "name" => campaign_name,
        "type" => "regular",
        "groups" => [group_id.to_s],
        "emails" => [email_obj_str]
      }
    },
    {
      "label" => "docs array+plain string-group",
      "body" => {
        "name" => campaign_name,
        "type" => "regular",
        "groups" => [group_id.to_s],
        "emails" => [base_plain_email]
      }
    },
    {
      "label" => "docs array+no-content string-group",
      "body" => {
        "name" => campaign_name,
        "type" => "regular",
        "groups" => [group_id.to_s],
        "emails" => [base_no_content_email]
      }
    },
    {
      "label" => "legacy object-index plain string-group",
      "body" => {
        "name" => campaign_name,
        "type" => "regular",
        "groups" => [group_id.to_s],
        "emails" => { "0" => base_plain_email }
      }
    }
  ]
  if group_id.to_s.match?(/\A\d+\z/)
    group_id_i = group_id.to_i
    attempts.concat([
      {
        "label" => "docs array+plain integer-group",
        "body" => {
          "name" => campaign_name,
          "type" => "regular",
          "groups" => [group_id_i],
          "emails" => [base_plain_email]
        }
      },
      {
        "label" => "docs array+no-content integer-group",
        "body" => {
          "name" => campaign_name,
          "type" => "regular",
          "groups" => [group_id_i],
          "emails" => [base_no_content_email]
        }
      },
      {
        "label" => "legacy object-index plain integer-group",
        "body" => {
          "name" => campaign_name,
          "type" => "regular",
          "groups" => [group_id_i],
          "emails" => { "0" => base_plain_email }
        }
      }
    ])
  end

  code = nil
  created = nil
  first_422 = nil
  attempts.each_with_index do |attempt, idx|
    create_body = attempt.fetch("body")
    code, created = http_json(:post, "/campaigns", token: token, body: create_body)
    if ENV["OSLOBYGDA_DEBUG"]
      warn "DEBUG create attempt #{idx + 1} payload: #{JSON.dump(create_body)}"
      warn "DEBUG create attempt #{idx + 1} response: status=#{code} body=#{created.inspect}"
    end
    break if (code == 200 || code == 201) && created && created.dig("data", "id")
    if code == 422
      first_422 ||= created
      warn "Create campaign attempt #{idx + 1} (#{attempt.fetch("label")}) failed with 422: #{created.inspect}"
      next
    end
    warn "Create campaign attempt #{idx + 1} (#{attempt.fetch("label")}) failed with status #{code}: #{created.inspect}"
    break
  end

  unless (code == 200 || code == 201) && created && created.dig("data", "id")
    error_body = first_422 || created
    msg = error_body&.dig("message") || error_body&.inspect || "no body"
    errors = error_body&.dig("errors")
    msg += " | errors: #{errors.inspect}" if errors
    hint = case code
    when 404
      " 404 often means wrong MAILERLITE_GROUP_ID or that campaign API is not available for your plan. Check Integrations → API in MailerLite for the correct group ID."
    when 422
      " 422: Tried documented and compatibility payload shapes for emails plus plain-text fallback. Set OSLOBYGDA_DEBUG=1 to log payload; see developers.mailerlite.com/docs/campaigns or contact MailerLite support."
    else
      ""
    end
    raise "Failed to create campaign (status=#{code}): #{msg}#{hint}"
  end

  campaign_id = created.dig("data", "id").to_s
  puts "Created campaign id=#{campaign_id}"
else
  puts "Found existing campaign '#{campaign_name}' (id=#{campaign_id}, status=#{existing['status']}). Sending now."
end

# Send immediately (delivery=instant)
schedule_body = { "delivery" => "instant" }
code, scheduled = http_json(:post, "/campaigns/#{campaign_id}/schedule", token: token, body: schedule_body)
unless code == 200 || code == 201
  raise "Failed to send/schedule campaign (status=#{code}): #{scheduled.inspect}"
end

puts "Sent campaign '#{campaign_name}' to group #{group_id}"
