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

def http_json(method, path, token:, body: nil)
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
  parsed =
    if res.body.nil? || res.body.strip.empty?
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
  (raw || []).filter_map do |e|
    dato = e["dato"] || e[:dato]
    next if dato.nil? || dato.to_s.strip.empty?
    {
      "uid" => (e["uid"] || e[:uid]).to_s,
      "dato" => Date.parse(dato.to_s)
    }
  end.sort_by { |e| e["dato"] }
end

token = env!("MAILERLITE_API_TOKEN")
campaign_id = env!("MAILERLITE_READY_CAMPAIGN_ID")

trigger_uid_contains = ENV.fetch("TRIGGER_UID_CONTAINS", "pobb-")
days_before = Integer(ENV.fetch("DAYS_BEFORE_TRIGGER", "7"))

today = Date.today
events = load_events
future = events.select { |e| e["dato"] >= today }
trigger = future.find { |e| e["uid"].include?(trigger_uid_contains) }

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

code, campaign = http_json(:get, "/campaigns/#{campaign_id}", token: token)
unless code == 200 && campaign && campaign.dig("data", "id")
  raise "Failed to fetch campaign #{campaign_id} (status=#{code}): #{campaign.inspect}"
end

status = campaign.dig("data", "status").to_s
name = campaign.dig("data", "name").to_s
allowed_statuses = %w[draft ready]

if status == "sent"
  puts "Campaign '#{name}' (id=#{campaign_id}) is already sent. Nothing to do."
  exit 0
end

unless allowed_statuses.include?(status)
  raise "Campaign '#{name}' (id=#{campaign_id}) has status='#{status}', expected one of #{allowed_statuses.join(", ")}."
end

schedule_body = { "delivery" => "instant" }
code, scheduled = http_json(:post, "/campaigns/#{campaign_id}/schedule", token: token, body: schedule_body)
unless code == 200 || code == 201
  msg = scheduled&.dig("message") || scheduled&.inspect || "no body"
  errors = scheduled&.dig("errors")
  msg += " | errors: #{errors.inspect}" if errors
  hint = if code == 422
           " Ensure campaign content and recipients are configured in MailerLite UI before this workflow runs."
         else
           ""
         end
  raise "Failed to send/schedule campaign id=#{campaign_id} (status=#{code}): #{msg}.#{hint}"
end

puts "Sent campaign '#{name}' (id=#{campaign_id})"
