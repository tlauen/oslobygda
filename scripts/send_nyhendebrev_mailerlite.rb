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
  uri = URI.join(API_BASE, path)
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

  return [res.code.to_i, nil] if res.body.nil? || res.body.strip.empty?
  [res.code.to_i, JSON.parse(res.body)]
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
  "<li>#{line}</li>"
end.join("\n")

html = <<~HTML
  <div>
    <h1>Komande tilskipingar</h1>
    <p>Her er det som ligg i kalenderen vår no:</p>
    <ul>
      #{html_items}
    </ul>
    <p>
      Sjå heile kalenderen: <a href="#{base_url}/kalender/">#{base_url}/kalender/</a><br>
      Kalender (ICS): <a href="#{base_url}/kalender.ics">#{base_url}/kalender.ics</a>
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

def campaign_exists?(token, campaign_name)
  %w[draft ready sent].any? do |status|
    code, data = http_json(:get, "/campaigns?filter[status]=#{status}&limit=100", token: token)
    next false unless code == 200 && data && data["data"].is_a?(Array)
    data["data"].any? { |c| c["name"].to_s == campaign_name }
  end
end

if campaign_exists?(token, campaign_name)
  puts "Campaign '#{campaign_name}' already exists. Not creating/sending again."
  exit 0
end

email_obj = {
  "subject" => subject,
  "from_name" => from_name,
  "from" => from_email,
  "content" => html,
  "plain_text" => plain
}
email_obj["reply_to"] = reply_to unless reply_to.empty?

create_body = {
  "name" => campaign_name,
  "type" => "regular",
  "groups" => [group_id],
  "emails" => [email_obj]
}

code, created = http_json(:post, "/campaigns", token: token, body: create_body)
unless code == 200 && created && created.dig("data", "id")
  raise "Failed to create campaign (status=#{code}): #{created.inspect}"
end

campaign_id = created.dig("data", "id").to_s
puts "Created campaign id=#{campaign_id}"

# Send immediately (delivery=instant)
schedule_body = { "delivery" => "instant" }
code, scheduled = http_json(:post, "/campaigns/#{campaign_id}/schedule", token: token, body: schedule_body)
unless code == 200
  raise "Failed to send/schedule campaign (status=#{code}): #{scheduled.inspect}"
end

puts "Sent campaign '#{campaign_name}' to group #{group_id}"
