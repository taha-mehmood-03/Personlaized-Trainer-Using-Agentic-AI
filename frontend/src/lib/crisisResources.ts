import { CrisisResource } from '@/lib/api'

export const DEFAULT_CRISIS_COUNTRY = 'PK'

export const PAKISTAN_CRISIS_RESOURCES: CrisisResource = {
    primary_hotline: {
        name: 'Umang Pakistan Mental Health Helpline',
        number: '+92-311-7786264',
        available: '24/7',
        call_text: 'Call',
        language: 'Urdu & English',
    },
    secondary_hotline: {
        name: 'Rescue / Ambulance',
        number: '1122',
        available: '24/7',
        call_text: 'Call',
        language: 'Pakistan emergency service',
    },
    tertiary_hotline: {
        name: 'Police Emergency',
        number: '15',
        available: '24/7',
        call_text: 'Call',
    },
    emergency_service: {
        name: 'Edhi Ambulance',
        number: '115',
        available: '24/7',
        call_text: 'Call',
    },
    text_line: {
        name: 'Crisis Support via WhatsApp',
        action: 'WhatsApp Umang: +92-311-7786264',
        available: '24/7',
        supported: true,
    },
    international: {
        name: 'International Association for Suicide Prevention',
        website: 'https://www.iasp.info/resources/Crisis_Centres/',
    },
    message:
        'If someone is in immediate physical danger in Pakistan, call Rescue/Ambulance 1122, Police 15, or Edhi Ambulance 115. For mental-health crisis support, contact Umang at +92-311-7786264.',
}
