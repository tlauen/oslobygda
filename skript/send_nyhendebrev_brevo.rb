#!/usr/bin/env ruby
# frozen_string_literal: true

require "yaml"
require "date"
require "json"
require "net/http"
require "uri"

API_BASE = "https://api.brevo.com/v3"

MONTHS_NN = [
  nil,
  "januar", "februar", "mars", "april", "mai", "juni",
  "juli", "august", "september", "oktober", "november", "desember"
].freeze

WEEKDAYS_NN = %w[sundag mandag tirsdag onsdag torsdag fredag laurdag].freeze

def env!(key)
  value = ENV[key]
  raise "Missing required env var #{key}" if value.nil? || value.strip.empty?

  value
end

def http_json(method, path, api_key:, body: nil)
  path = path.sub(/\A\//, "")
  uri = URI.join(API_BASE + "/", path)
  req = case method
        when :get then Net::HTTP::Get.new(uri)
        when :post then Net::HTTP::Post.new(uri)
        else
          raise "Unsupported method #{method}"
        end

  req["api-key"] = api_key
  req["Accept"] = "application/json"
  if body
    req["Content-Type"] = "application/json"
    req.body = JSON.dump(body)
  end

  res = Net::HTTP.start(uri.host, uri.port, use_ssl: true) { |http| http.request(req) }
  parsed = if res.body.nil? || res.body.strip.empty?
             nil
           else
             JSON.parse(res.body)
           end
  [res.code.to_i, parsed]
rescue JSON::ParserError
  [res.code.to_i, { "message" => res.body }]
end

def load_events
  raw = YAML.load_file(File.join(__dir__, "..", "_data", "kalender.yml"))
  (raw || []).filter_map do |event|
    date_raw = event["dato"] || event[:dato]
    next if date_raw.nil? || date_raw.to_s.strip.empty?

    {
      "uid" => (event["uid"] || event[:uid]).to_s,
      "dato" => Date.parse(date_raw.to_s),
      "start" => (event["start"] || event[:start]).to_s,
      "tittel" => (event["tittel"] || event[:tittel]).to_s,
      "stad" => (event["stad"] || event[:stad]).to_s
    }
  end.sort_by { |event| event["dato"] }
end

def fmt_date_nn(date)
  "#{date.day}. #{MONTHS_NN.fetch(date.month)} #{date.year}"
end

def fmt_subject_date_nn(date)
  "#{WEEKDAYS_NN[date.wday]} #{date.day}. #{MONTHS_NN.fetch(date.month)}"
end

def get_campaigns(api_key)
  code, body = http_json(:get, "/emailCampaigns?limit=100&offset=0&sort=desc", api_key: api_key)
  unless code == 200 && body && body["campaigns"].is_a?(Array)
    raise "Could not list Brevo campaigns (status=#{code}): #{body.inspect}"
  end

  body["campaigns"]
end

def find_campaign_by_name(campaigns, name)
  campaigns.find { |campaign| campaign["name"].to_s == name.to_s }
end

def list_exists?(api_key, list_id)
  code, body = http_json(:get, "/contacts/lists/#{list_id}", api_key: api_key)
  code == 200 && body && body["id"]
end

api_key = env!("BREVO_API_KEY")
from_email = env!("BREVO_FROM_EMAIL")
from_name = env!("BREVO_FROM_NAME")
reply_to = ENV.fetch("BREVO_REPLY_TO", "").strip
# Vanleg: BREVO_LIST_ID = hovudlista «Nyhendebrev». Test: BREVO_BRUK_TEST_LISTE=1 og BREVO_TEST_LIST_ID = lista «Test».
bruk_test_liste = %w[1 true yes].include?(ENV["BREVO_BRUK_TEST_LISTE"].to_s.strip.downcase)
list_id =
  if bruk_test_liste
    Integer(env!("BREVO_TEST_LIST_ID"))
  else
    Integer(env!("BREVO_LIST_ID"))
  end

base_url = ENV.fetch("OSLOBYGDA_BASE_URL", "https://oslobygda.no").sub(%r{/\z}, "")
trigger_uid_contains = ENV.fetch("TRIGGER_UID_CONTAINS", "pobb-")
days_before = Integer(ENV.fetch("DAYS_BEFORE_TRIGGER", "7"))
limit = Integer(ENV.fetch("UPCOMING_LIMIT", "12"))

events = load_events
today = Date.today
future = events.select { |event| event["dato"] >= today }
trigger = future.find { |event| event["uid"].include?(trigger_uid_contains) }

if trigger.nil?
  puts "No upcoming event matching trigger uid '#{trigger_uid_contains}'. Nothing to do."
  exit 0
end

trigger_date = trigger.fetch("dato")
send_on = trigger_date - days_before
force_send = %w[1 true yes].include?(ENV["OSLOBYGDA_FORCE_SEND"].to_s.strip.downcase)

unless force_send || today == send_on
  puts "Today is #{today}, next trigger event is #{trigger_date} (send_on=#{send_on}). Not sending today."
  exit 0
end
puts "Force send mode – sending despite send_on=#{send_on}" if force_send && today != send_on

unless list_exists?(api_key, list_id)
  raise "Brevo list #{list_id} was not found for API key."
end
if bruk_test_liste
  puts "Utsending til testlista (BREVO_TEST_LIST_ID=#{list_id}, t.d. «Test» i Brevo)."
else
  puts "Utsending til hovudlista for nyhendebrev (BREVO_LIST_ID=#{list_id}, t.d. «Nyhendebrev» i Brevo)."
end

upcoming = future.first(limit)
subject = "Neste folkemusikkpøbb er #{fmt_subject_date_nn(trigger_date)}!"
# Eige namn for test slik at test- og hovudkampanje ikkje forvekslast (Brevo bind mottakarar til kampanje).
campaign_name = if bruk_test_liste
  "Test – nyhendebrev – tilskipingar – #{trigger_date.iso8601}"
else
  "Nyhendebrev – tilskipingar – #{trigger_date.iso8601}"
end

# Idempotens: hovudlista skal ikkje få dobbel utsending same dato. På testlista er same
# kampanjenamn ofte allerei `sendt` når du prøver igjen; med force_send får kvar køyring eit
# unikt suffiks så Brevo opprettar ny kampanje.
campaigns = get_campaigns(api_key)
existing_campaign = find_campaign_by_name(campaigns, campaign_name)
if bruk_test_liste && existing_campaign && existing_campaign["status"].to_s.downcase == "sent" && force_send
  campaign_name = "#{campaign_name} – køyring-#{Time.now.getutc.strftime('%Y%m%d-%H%M%S')}"
  puts "Testliste: fann allerei sendt kampanje med same dato; nytt unikt namn: #{campaign_name}"
  existing_campaign = find_campaign_by_name(get_campaigns(api_key), campaign_name)
end

if existing_campaign && existing_campaign["status"].to_s.downcase == "sent"
  puts "Campaign '#{campaign_name}' already sent in Brevo. Not sending again."
  exit 0
end

html_items = upcoming.map do |event|
  line = +"<strong>#{fmt_date_nn(event["dato"])}</strong>"
  line << " kl. #{event["start"]}" unless event["start"].empty?
  line << " – #{event["tittel"]}" unless event["tittel"].empty?
  line << " (#{event["stad"]})" unless event["stad"].empty?
  "<li style=\"margin:.5em 0; padding-left:.5em; border-left:3px solid #BFEAEE; list-style:none;\">#{line}</li>"
end.join("\n")

html = <<~HTML
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#E8E6E3" style="width:100%; border-collapse:collapse; margin:0; background-color:#E8E6E3;">
    <tr>
      <td align="center" bgcolor="#E8E6E3" style="padding:24px 16px; background-color:#E8E6E3;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#FCF9F3" style="max-width:680px; width:100%; border-collapse:collapse; background-color:#FCF9F3;">
          <tr>
            <td style="padding:36px 32px; font-family:Georgia,'Times New Roman',serif; color:#12110e; line-height:1.5; font-size:16px;">
              <p style="margin:0 0 4px; font-family:Georgia,serif; font-weight:700; font-size:1.3em; letter-spacing:.02em;">Oslobygda kulturlag</p>
              <p style="margin:0 0 24px; font-size:0.95em; color:#5a5856;">frilynt · folkeleg · litt for seint heim</p>
              <h1 style="margin:0 0 14px; font-family:Georgia,serif; font-weight:700; font-size:1.6em; line-height:1.25; color:#12110e;">Komande tilskipingar</h1>
              <p style="margin:0 0 16px; line-height:1.5;">Her er det som ligg i kalenderen vår no:</p>
              <ul style="margin:0 0 22px; padding-left:0; line-height:1.65; list-style:none;">
                #{html_items}
              </ul>
              <p style="margin:0 0 8px; line-height:1.5;">
                Sjå heile kalenderen: <a href="#{base_url}/kalender/" style="color:#2f5d50; text-decoration:underline;">#{base_url}/kalender/</a><br>
                Kalender (ICS): <a href="#{base_url}/kalender.ics" style="color:#2f5d50; text-decoration:underline;">#{base_url}/kalender.ics</a>
              </p>
              <p style="margin:24px 0 0; text-align:center;">
                <a href="#{base_url}/" style="text-decoration:none;"><img src="#{base_url}/lutar/bilete/logo_oslobygda.png" alt="Oslobygda kulturlag" width="200" height="200" style="display:inline-block; width:200px; height:200px; max-width:100%;"></a>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
HTML

payload = {
  "name" => campaign_name,
  "subject" => subject,
  "type" => "classic",
  "sender" => { "name" => from_name, "email" => from_email },
  "htmlContent" => html,
  "recipients" => { "listIds" => [list_id] }
}
payload["replyTo"] = reply_to unless reply_to.empty?

campaign_id =
  if existing_campaign
    puts "Found existing campaign '#{campaign_name}' (id=#{existing_campaign["id"]}, status=#{existing_campaign["status"]}). Reusing."
    existing_campaign["id"]
  else
    code, created = http_json(:post, "/emailCampaigns", api_key: api_key, body: payload)
    unless (code == 200 || code == 201) && created && created["id"]
      raise "Failed to create Brevo campaign (status=#{code}): #{created.inspect}"
    end
    puts "Created Brevo campaign id=#{created["id"]}"
    created["id"]
  end

kode, sendt = http_json(:post, "/emailCampaigns/#{campaign_id}/sendNow", api_key: api_key)
unless kode == 200 || kode == 201 || kode == 202 || kode == 204
  raise "Failed to send Brevo campaign id=#{campaign_id} (status=#{kode}): #{sendt.inspect}"
end

puts "Sendte Brevo-kampanjen «#{campaign_name}» til mottakarliste id=#{list_id}"
